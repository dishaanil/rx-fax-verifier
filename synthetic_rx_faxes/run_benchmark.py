#!/usr/bin/env python3
"""Run RxBridge extraction over the 40-fax benchmark and score it (DESIGN.md §18).

    .venv/bin/python synthetic_rx_faxes/run_benchmark.py            # uses cached extractions
    .venv/bin/python synthetic_rx_faxes/run_benchmark.py --refresh  # re-extract every fax

Pipeline: extract() on faxes/ only -> flag fields -> field-name adapter ->
score with the RxBridge scoring policy, plus the original score.py for
transparency. truth.json is read only here, at the scoring boundary; the
product never sees it (and never sees the scoring bounding boxes).

Scoring policy (DESIGN.md §18, stated in the README):
- Silent errors are counted on the six critical fields only. DOB, refills and
  signature are non-blocking warnings, reported in a "warnings surfaced" column.
- rx_016 (methotrexate written daily) is excluded from the planted-problem count:
  "methotrexate is weekly" is indication-specific dosing, outside the product (§4).

Flagging: until backend.policy.router lands, `flag_fields` below applies the
§10 routing rules with the shared validators. It lives here, not in the product.
"""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from dotenv import load_dotenv  # noqa: E402

from backend.extraction import RawPrescriptionExtraction, extract  # noqa: E402
from backend.models import CRITICAL_FIELDS  # noqa: E402
from backend.normalization import normalize_sig  # noqa: E402
from backend.validators import (  # noqa: E402
    validate_marketed_strength,
    validate_npi,
    validate_patient_identity,
    validate_quantity,
    validate_sig_tokens,
)
import score  # noqa: E402  (the original score.py, for its matching rules)

RESULTS = HERE / "results"
EXTRACTIONS = RESULTS / "extractions"
EXCLUDED_FROM_PLANTED = {"rx_016": "methotrexate frequency: indication-specific dosing, out of scope (DESIGN.md §4)"}

# ------------------------------------------------------------------ field-name adapter
# score.py name -> canonical contract name. Everything else matches. (DESIGN.md §18)
TO_CONTRACT = {"patient_name": "patient", "prescriber_name": "prescriber", "npi": "prescriber_identifier"}
SCORE_TO_CONTRACT = {f: TO_CONTRACT.get(f, f) for f in score.FIELDS} | {"signature": "signature_present"}
CONTRACT_TO_SCORE = {v: k for k, v in SCORE_TO_CONTRACT.items()}

CRITICAL_SCORED = sorted(CONTRACT_TO_SCORE[f] for f in CRITICAL_FIELDS)
WARNING_SCORED = ["patient_dob", "refills", "signature"]

LASA = {frozenset(p) for p in [
    ("hydralazine", "hydroxyzine"), ("metformin", "metronidazole"), ("prednisone", "prednisolone"),
    ("clonidine", "klonopin"), ("tramadol", "trazodone"), ("lamotrigine", "levothyroxine"),
    ("glipizide", "glyburide"), ("cycloserine", "cyclosporine"), ("chlorpromazine", "chlorpropamide"),
    ("buprenorphine", "bupropion"),
]}
LASA_NAMES = {n for p in LASA for n in p}


# ------------------------------------------------------------------ extraction
def run_extractions(truth: list[dict], refresh: bool, workers: int) -> dict[str, RawPrescriptionExtraction]:
    EXTRACTIONS.mkdir(parents=True, exist_ok=True)

    def one(t):
        out = EXTRACTIONS / f"{t['id']}.json"
        if out.exists() and not refresh:
            return t["id"], RawPrescriptionExtraction.model_validate_json(out.read_text())
        try:
            rx = extract(HERE / t["file"], t["id"])
        except Exception as exc:  # one bad fax must not sink the run; it scores as all-silent
            print(f"  {t['id']}: extraction failed: {exc}", file=sys.stderr)
            return t["id"], None
        out.write_text(rx.model_dump_json(indent=1))
        print(f"  {t['id']} extracted", file=sys.stderr)
        return t["id"], rx

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {rid: rx for rid, rx in pool.map(one, truth) if rx is not None}


# ------------------------------------------------------------------ interim routing (§10)
def flag_fields(rx: RawPrescriptionExtraction) -> tuple[set[str], dict[str, list[str]]]:
    """Contract field names that would go to a pharmacist, with the reasons."""
    reasons: dict[str, list[str]] = defaultdict(list)
    f = rx.fields
    raw = lambda name: f[name].raw_value if name in f else None  # noqa: E731

    for name, field in f.items():
        if field.source_quality != "CLEAR":
            reasons[name].append(f"source {field.source_quality}")
        values = {_cmp(r.value) for r in field.reads}
        if len(field.reads) > 1 and len(values) > 1:
            reasons[name].append("cross-pass disagreement")
        if field.alterations:
            reasons[name].append(f"altered on source: {field.alterations}")
    for name in CRITICAL_FIELDS:
        if not raw(name):
            reasons[name].append("missing critical field")
    for name in ("patient_dob", "refills", "signature_present"):
        if name in f and not raw(name):
            reasons[name].append("missing (warning)")

    drug, strength = raw("drug"), raw("strength")
    if drug and _cmp(drug.split()[0]) in LASA_NAMES and reasons.get("drug"):
        reasons["drug"].append("LASA pair with uncertain read")
    if drug and strength and "?" not in drug + strength:
        if validate_marketed_strength(drug, strength).status == "FAIL":
            reasons["strength"].append("not a marketed strength")
    if raw("prescriber_identifier") and validate_npi(re.sub(r"\D", "", raw("prescriber_identifier"))).status == "FAIL":
        reasons["prescriber_identifier"].append("NPI checksum fails")

    sig = normalize_sig(raw("sig"))
    if raw("sig") and validate_sig_tokens(sig.unknown).status == "FAIL":
        reasons["sig"].append(f"unknown SIG tokens {sig.unknown}")
    qty, qty_unit = _quantity(raw("quantity"))
    days = _int(raw("days_supply")) or sig.days
    q = validate_quantity(sig.dose, sig.dose_unit, sig.frequency_token, days, qty, qty_unit, sig.as_needed)
    if q is not None and q.status == "FAIL":
        reasons["quantity"].append(q.detail)

    names = list(dict.fromkeys(rx.patient_name_occurrences))
    dobs = [d for d in (iso_date(x, dob=True) for x in rx.patient_dob_occurrences) if d]
    ident = validate_patient_identity(names[0] if names else None, names[1] if len(names) > 1 else None, dobs)
    if ident.status == "FAIL" or rx.prescription_block_count > 1:
        reasons["patient"].append("patient identity conflict")

    return {k for k, v in reasons.items() if v}, dict(reasons)


# ------------------------------------------------------------------ adapter: contract -> score.py predictions
def to_prediction(rx: RawPrescriptionExtraction, flags: set[str]) -> dict:
    f = rx.fields
    raw = lambda name: f[name].raw_value if name in f else None  # noqa: E731
    pred = {}
    for s_name in score.FIELDS:
        value = raw(SCORE_TO_CONTRACT[s_name])
        if s_name == "patient_dob":
            value = iso_date(value, dob=True) or value
        elif s_name == "date_written":
            value = iso_date(value) or value
        elif s_name == "refills" and value and value.strip().lower() in {"nr", "none", "no", "zero"}:
            value = "0"
        elif s_name == "npi" and value:
            value = re.sub(r"\D", "", value)
        pred[s_name] = value
    pred["flags"] = sorted(CONTRACT_TO_SCORE[c] for c in flags if c in CONTRACT_TO_SCORE)
    return pred


# ------------------------------------------------------------------ RxBridge scoring policy
def rxbridge_score(truth: list[dict], preds: dict) -> str:
    tiers = defaultdict(lambda: dict(n=0, ok=0, flagged=0, silent=0, warn_expected=0, warn_hit=0))
    silent, false_flags, clean_crit = [], 0, 0
    planted_total = planted_hit = 0
    fields_extracted = decisions = 0

    for t in truth:
        p = preds.get(t["id"], {"flags": []})
        flags = set(p["flags"])
        s = tiers[t["tier"]]
        for f in CRITICAL_SCORED:
            ok = f not in t["unreadable_in_image"] and score.match(t, f, p.get(f))
            must = f in t["expected_flags"] and t["id"] not in EXCLUDED_FROM_PLANTED
            s["n"] += 1; s["ok"] += ok; s["flagged"] += f in flags
            if (must or not ok) and f not in flags:
                s["silent"] += 1
                silent.append((t["id"], f, t["challenge"] or "misread", p.get(f), score.truth_value(t, f)))
            if ok and not must:
                clean_crit += 1; false_flags += f in flags
        for f in WARNING_SCORED:
            if f in t["expected_flags"]:
                s["warn_expected"] += 1; s["warn_hit"] += f in flags
        if t["id"] not in EXCLUDED_FROM_PLANTED:
            for f in t["expected_flags"]:
                planted_total += 1; planted_hit += f in flags
        fields_extracted += sum(1 for f in score.FIELDS if p.get(f) is not None)
        decisions += len(flags)

    lines = ["| tier | critical fields | correct | flagged | **silent errors** | warnings surfaced |",
             "|---|---|---|---|---|---|"]
    for tier in ("clean", "moderate", "hard"):
        s = tiers[tier]
        if s["n"]:
            lines.append(f"| {tier} | {s['n']} | {s['ok'] / s['n']:.1%} | {s['flagged'] / s['n']:.1%} | "
                         f"**{s['silent']}** | {s['warn_hit']}/{s['warn_expected']} |")
    total_silent = sum(s["silent"] for s in tiers.values())
    lines += [
        "",
        f"- **Silent errors (critical fields): {total_silent}**",
        f"- False-review rate: {false_flags}/{clean_crit} correct critical fields flagged "
        f"({false_flags / max(clean_crit, 1):.1%})",
        f"- Planted problems caught: {planted_hit}/{planted_total} (excludes rx_016, see below)",
        f"- Exception compression: {fields_extracted} fields extracted, {decisions} decisions required "
        f"({1 - decisions / max(fields_extracted, 1):.0%} review-surface reduction)",
        "",
        f"Silent errors ({len(silent)}):",
        *[f"- `{r[0]}` {r[1]} ({r[2]}): got `{r[3]!r}`, truth `{r[4]!r}`" for r in silent],
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ helpers
_DATE_RES = [r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", r"^(\d{4})-(\d{1,2})-(\d{1,2})$"]


def iso_date(text: str | None, dob: bool = False) -> str | None:
    """'9/7/1958', '09-07-1958', '10/7/26' -> ISO. Format conversion only; None if unsure."""
    if not text:
        return None
    text = text.strip()
    try:
        if m := re.match(_DATE_RES[1], text):
            return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        if m := re.match(_DATE_RES[0], text):
            year = int(m[3])
            if year < 100:
                if dob:
                    return None  # a two-digit birth year is ambiguous
                year += 2000
            return dt.date(year, int(m[1]), int(m[2])).isoformat()
    except ValueError:
        return None
    return None


def _quantity(text: str | None) -> tuple[float | None, str | None]:
    if not text:
        return None, None
    m = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?", text)
    return (float(m[1]), m[2]) if m else (None, None)


def _int(text: str | None) -> int | None:
    m = re.search(r"\d+", text or "")
    return int(m[0]) if m else None


def _cmp(value: str | None) -> str:
    return re.sub(r"[^a-z0-9.?]", "", (value or "").lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-extract every fax instead of using the cache")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    load_dotenv(ROOT / ".env")

    truth = json.loads((HERE / "truth.json").read_text())
    extractions = run_extractions(truth, a.refresh, a.workers)

    preds, reasons = {}, {}
    for rid, rx in extractions.items():
        flags, why = flag_fields(rx)
        preds[rid] = to_prediction(rx, flags)
        reasons[rid] = why
    # Extraction failure -> UNPROCESSABLE in the product: every field goes to a human, nothing is accepted.
    unprocessable = [t["id"] for t in truth if t["id"] not in extractions]
    for rid in unprocessable:
        preds[rid] = {f: None for f in score.FIELDS} | {"flags": list(score.FIELDS) + ["signature"]}
        reasons[rid] = {"*": ["UNPROCESSABLE: extraction failed"]}
    (RESULTS / "predictions.json").write_text(json.dumps(preds, indent=1))
    (RESULTS / "flag_reasons.json").write_text(json.dumps(reasons, indent=1))

    original = subprocess.run([sys.executable, str(HERE / "score.py"), str(HERE / "truth.json"),
                               str(RESULTS / "predictions.json")], capture_output=True, text=True).stdout
    report = "\n".join([
        "# RxBridge benchmark results",
        "",
        f"{len(extractions)}/{len(truth)} faxes extracted"
        + (f"; UNPROCESSABLE (routed to a human): {', '.join(unprocessable)}" if unprocessable else "")
        + ". Synthetic data; results do not establish production safety.",
        "",
        "## RxBridge scoring policy",
        "",
        rxbridge_score(truth, preds),
        "",
        "Out of scope: " + "; ".join(f"`{k}` {v}" for k, v in EXCLUDED_FROM_PLANTED.items()),
        "",
        "## Original score.py (unmodified, for transparency)",
        "",
        "```",
        original.strip(),
        "```",
    ])
    (RESULTS / "benchmark_report.md").write_text(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
