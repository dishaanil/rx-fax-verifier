#!/usr/bin/env python3
"""Score extraction output against truth.json.

    python3 score.py dataset/truth.json predictions.json

predictions.json maps each id to the extracted fields plus the fields your system flagged for review:
  {"rx_001": {"patient_name": "...", "patient_dob": "1953-06-20", "drug": "...", "strength": "10 mg",
              "sig": "...", "quantity": 10, "refills": 0, "prescriber_name": "...", "npi": "...",
              "date_written": "2026-10-06", "flags": ["strength"]}}

The number that matters most is SILENT ERRORS: a field that is wrong (or should have been flagged)
and was not flagged. That is the case where a pharmacist would never have been asked to look.
"""
import json, re, sys
from collections import defaultdict

FIELDS = ["patient_name", "patient_dob", "drug", "strength", "sig", "quantity", "refills",
          "prescriber_name", "npi", "date_written"]


def norm(v):
    return "" if v is None else re.sub(r"[^a-z0-9.]+", " ", str(v).lower()).strip()


def truth_value(t, f):
    return {"patient_name": t["patient"]["name"], "patient_dob": t["patient"]["dob"], "drug": t["medication"]["drug"],
            "strength": t["medication"]["strength"], "sig": t["sig_normalized"], "quantity": t["quantity"],
            "refills": t["refills"], "prescriber_name": t["prescriber"]["name"], "npi": t["prescriber"]["npi"],
            "date_written": t["date_written"]}[f]


def match(t, f, pred):
    want = truth_value(t, f)
    if f == "sig":  # free text: accept the abbreviated or the expanded form, or 80% token overlap
        p = set(norm(pred).split())
        for cand in (t["sig_normalized"], t["sig_as_written"]):
            c = set(norm(cand).split())
            if c and len(p & c) / len(p | c) >= 0.8:
                return True
        return False
    if f == "strength":
        return norm(pred).replace(" ", "") == norm(want).replace(" ", "")
    if f == "prescriber_name":
        return norm(want) in norm(pred) or norm(pred) == norm(want)
    return norm(pred) == norm(want)


def main():
    truth = json.load(open(sys.argv[1])); preds = json.load(open(sys.argv[2]))
    by_tier = defaultdict(lambda: dict(n=0, ok=0, silent=0, flagged=0))
    by_field = defaultdict(lambda: [0, 0])
    exp_total = exp_hit = false_flags = clean_fields = 0
    silent = []
    for t in truth:
        p = preds.get(t["id"], {}); flags = set(p.get("flags", [])); s = by_tier[t["tier"]]
        for f in FIELDS:
            unreadable = f in t["unreadable_in_image"]
            ok = (not unreadable) and match(t, f, p.get(f))
            must_flag = f in t["expected_flags"]
            s["n"] += 1; s["ok"] += ok; s["flagged"] += f in flags
            by_field[f][0] += ok; by_field[f][1] += 1
            if (must_flag or not ok) and f not in flags:
                s["silent"] += 1; silent.append((t["id"], f, t["challenge"] or "misread", p.get(f), truth_value(t, f)))
            if not must_flag and ok:
                clean_fields += 1; false_flags += f in flags
        for f in t["expected_flags"]:
            exp_total += 1; exp_hit += f in flags
    print(f"{'tier':10}{'fields':>8}{'correct':>10}{'flagged':>10}{'SILENT ERRORS':>16}")
    for tier in ("clean", "moderate", "hard"):
        s = by_tier[tier]
        if s["n"]:
            print(f"{tier:10}{s['n']:>8}{s['ok'] / s['n']:>10.1%}{s['flagged'] / s['n']:>10.1%}{s['silent']:>16}")
    print("\nper-field accuracy: " + ", ".join(f"{f} {a / n:.0%}" for f, (a, n) in by_field.items()))
    print(f"planted problems caught: {exp_hit}/{exp_total}")
    print(f"unnecessary flags on correct fields: {false_flags}/{clean_fields}")
    print(f"\nsilent errors ({len(silent)}):")
    for row in silent:
        print("  %s %-16s %-18s got=%r truth=%r" % row)


if __name__ == "__main__":
    main()
