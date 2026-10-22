"""Demo pharmacy stock: an in-memory SQLite database loaded from fixtures/inventory.json.

Real queries, the same answer every run, no setup. Fills change the in-memory
copy only, so stock resets on restart. A real pharmacy system (or a hosted
database) would replace this class behind the same three methods.
"""

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from backend.references.strengths import drug_base_key, normalize_strength

INVENTORY_FILE = Path(__file__).resolve().parents[2] / "fixtures" / "inventory.json"

_FORMS = {
    "tab": "tablet", "tabs": "tablet", "tablet": "tablet", "tablets": "tablet",
    "cap": "capsule", "caps": "capsule", "capsule": "capsule", "capsules": "capsule",
    "susp": "suspension", "suspension": "suspension", "oral suspension": "suspension",
}
# Form words sometimes written into the drug name ("amoxicillin suspension").
_FORM_WORDS_RE = re.compile(r"\s+(?:oral\s+)?(?:tablets?|tabs?|capsules?|caps?|suspension|susp)$")


def form_key(form: str | None) -> str | None:
    return _FORMS.get(re.sub(r"\s+", " ", (form or "").strip().casefold()).rstrip("."))


def drug_key(drug: str) -> str:
    return _FORM_WORDS_RE.sub("", drug_base_key(drug))


@dataclass(frozen=True)
class Product:
    product_id: int
    drug: str
    strength: str
    form: str
    unit: str
    on_hand: float
    location: str
    supplier_eta: str


class InventoryError(RuntimeError):
    pass


class SqliteInventory:
    def __init__(self, path: Path = INVENTORY_FILE) -> None:
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute("""CREATE TABLE products (
            product_id INTEGER PRIMARY KEY, drug TEXT, strength TEXT, form TEXT, unit TEXT,
            on_hand REAL CHECK (on_hand >= 0), location TEXT, supplier_eta TEXT,
            drug_key TEXT, strength_key TEXT, form_key TEXT)""")
        try:
            products = json.loads(path.read_text())["products"]
        except (OSError, ValueError, KeyError) as exc:
            raise InventoryError(f"Could not load inventory from {path}: {exc}") from exc
        self._db.executemany(
            "INSERT INTO products (drug, strength, form, unit, on_hand, location, supplier_eta,"
            " drug_key, strength_key, form_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(p["drug"], p["strength"], p["form"], p["unit"], p["on_hand"], p["location"], p["supplier_eta"],
              drug_key(p["drug"]), normalize_strength(p["strength"]), form_key(p["form"])) for p in products],
        )

    def find(self, drug: str, strength: str, form: str | None = None) -> list[Product]:
        """Products matching drug and strength exactly (after normalisation), narrowed by form when known."""
        strength_key = normalize_strength(strength)
        if strength_key is None:
            return []
        query = "SELECT * FROM products WHERE drug_key = ? AND strength_key = ?"
        args: list = [drug_key(drug), strength_key]
        if form_key(form):
            query += " AND form_key = ?"
            args.append(form_key(form))
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
        return [Product(*row[:8]) for row in rows]

    def get(self, product_id: int) -> Product | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
        return Product(*row[:8]) if row else None

    def dispense(self, product_id: int, quantity: float) -> Product:
        """Take `quantity` off the shelf; refuses (no change) if there isn't that much."""
        with self._lock:
            cursor = self._db.execute(
                "UPDATE products SET on_hand = on_hand - ? WHERE product_id = ? AND on_hand >= ?",
                (quantity, product_id, quantity),
            )
            if cursor.rowcount != 1:
                raise InventoryError("Not enough stock on hand.")
            row = self._db.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
        return Product(*row[:8])
