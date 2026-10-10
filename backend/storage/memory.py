"""In-memory store. State is lost on restart; no database, no external storage."""

import threading

from backend.models import Prescription, RxException


class MemoryStore:
    def __init__(self) -> None:
        self._prescriptions: dict[str, Prescription] = {}
        self._hashes: set[str] = set()
        self._reserved: set[str] = set()
        # Re-entrant so a service can hold it across get -> mutate -> save.
        self.lock = threading.RLock()

    def save(self, prescription: Prescription) -> None:
        with self.lock:
            self._prescriptions[prescription.prescription_id] = prescription.model_copy(deep=True)
            self._reserved.discard(prescription.prescription_id)

    def get(self, prescription_id: str) -> Prescription | None:
        with self.lock:
            rx = self._prescriptions.get(prescription_id)
            return rx.model_copy(deep=True) if rx else None

    def list(self) -> list[Prescription]:
        with self.lock:
            return [rx.model_copy(deep=True) for rx in self._prescriptions.values()]

    def find_exception(self, exception_id: str) -> tuple[Prescription, RxException] | None:
        with self.lock:
            for rx in self._prescriptions.values():
                for exc in rx.exceptions:
                    if exc.exception_id == exception_id:
                        copy = rx.model_copy(deep=True)
                        return copy, next(e for e in copy.exceptions if e.exception_id == exception_id)
            return None

    def reserve_id(self, base: str) -> str:
        """`base`, or `base_2`, `base_3`, ... — never an id already stored or reserved."""
        with self.lock:
            candidate, n = base, 1
            while candidate in self._prescriptions or candidate in self._reserved:
                n += 1
                candidate = f"{base}_{n}"
            self._reserved.add(candidate)
            return candidate

    def mark_hash_seen(self, sha256: str) -> None:
        with self.lock:
            self._hashes.add(sha256)

    def hash_seen(self, sha256: str) -> bool:
        with self.lock:
            return sha256 in self._hashes

    def seen_hashes(self) -> set[str]:
        with self.lock:
            return set(self._hashes)
