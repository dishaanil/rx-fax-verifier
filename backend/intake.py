"""Intake: id assignment, upload storage, extraction, processing, storage."""

import hashlib
import logging
import re
from pathlib import Path

from backend.extraction import ExtractionProvider
from backend.models import Prescription, PrescriptionStatus
from backend.pipeline import Clock, append_event, process, utc_now
from backend.storage import MemoryStore

log = logging.getLogger(__name__)

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(filename: str | None) -> str:
    name = _UNSAFE_RE.sub("_", Path(filename or "").name).lstrip(".")
    return name or "upload"


def intake(
    store: MemoryStore,
    extractor: ExtractionProvider,
    filename: str | None,
    data: bytes,
    upload_dir: Path | None,
    clock: Clock = utc_now,
) -> Prescription:
    """Assign an id from the filename stem (suffixing _2, _3, ... if taken), save
    the upload under upload_dir/<id>/, extract, process and store. Extractor
    failure yields an UNPROCESSABLE prescription, not an error. When upload_dir
    is None (seeding) nothing is written to disk."""
    name = safe_filename(filename)
    prescription_id = store.reserve_id(Path(name).stem or "upload")
    sha256 = hashlib.sha256(data).hexdigest()

    original_path: str | None = None
    if upload_dir is not None:
        target = upload_dir / prescription_id / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        original_path = str(target.resolve())

    try:
        raw = extractor.extract(original_path or name, prescription_id)
    except Exception as exc:  # any provider failure becomes UNPROCESSABLE
        log.warning("Extraction failed for %s: %s", prescription_id, exc)
        rx = _unprocessable(prescription_id, sha256, original_path, str(exc), clock)
        store.save(rx)
        return rx

    source = {**raw.source}
    if original_path is not None:
        source["original_path"] = original_path
    raw = raw.model_copy(update={"prescription_id": prescription_id, "source": source})

    with store.lock:
        rx = process(raw, store.seen_hashes(), sha256, clock)
        store.mark_hash_seen(sha256)
        store.save(rx)
    return rx


def _unprocessable(prescription_id: str, sha256: str, original_path: str | None, detail: str, clock: Clock) -> Prescription:
    source = {"type": "upload", "sha256": sha256}
    if original_path is not None:
        source["original_path"] = original_path
    rx = Prescription(
        prescription_id=prescription_id,
        status=PrescriptionStatus.UNPROCESSABLE,
        source=source,
        fields={},
        exceptions=[],
        clarifications=[],
        approved_by=None,
        audit_events=[],
    )
    append_event(rx, clock, "SYSTEM", "DOCUMENT_RECEIVED")
    append_event(rx, clock, "SYSTEM", "EXTRACTION_FAILED", detail=detail)
    return rx
