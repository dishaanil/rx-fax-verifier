"""Stock check for one prescription: is it on the shelf, where, and what can the pharmacist do.

Runs only on values a pharmacist can rely on: drug, strength and quantity must
be VERIFIED or set by the pharmacist. Looking up a misread ("metoprolol 15 mg")
would report false stock or the wrong shelf. Never affects approval.
"""

import re
from enum import StrEnum

from pydantic import BaseModel

from backend.inventory.store import Product, SqliteInventory
from backend.models import FieldDecision, Prescription
from backend.pipeline import field_value

REQUIRED = ("drug", "strength", "quantity")
_RELIABLE = (FieldDecision.VERIFIED, FieldDecision.HUMAN_VERIFIED)
_QUANTITY_RE = re.compile(r"^#?\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)?\.?$")
_COUNT_UNITS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules"}


class StockStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    PARTIAL = "PARTIAL"            # some on hand, not enough
    OUT_OF_STOCK = "OUT_OF_STOCK"  # carried, none on hand
    NOT_STOCKED = "NOT_STOCKED"    # this pharmacy doesn't carry the product
    NOT_CHECKED = "NOT_CHECKED"    # values not settled yet, or quantity can't be compared


class FillAction(StrEnum):
    FILL = "FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    ORDER = "ORDER"
    TRANSFER = "TRANSFER"


OPTIONS = {
    StockStatus.IN_STOCK: [FillAction.FILL],
    StockStatus.PARTIAL: [FillAction.PARTIAL_FILL, FillAction.ORDER, FillAction.TRANSFER],
    StockStatus.OUT_OF_STOCK: [FillAction.ORDER, FillAction.TRANSFER],
    StockStatus.NOT_STOCKED: [FillAction.ORDER, FillAction.TRANSFER],
    StockStatus.NOT_CHECKED: [],
}
SPECIAL_ORDER_ETA = "in 2-3 business days (special order)"


class StockCheck(BaseModel):
    status: StockStatus
    message: str
    product_id: int | None = None
    product: str | None = None       # "Metoprolol tartrate 75 mg tablet"
    location: str | None = None
    on_hand: float | None = None
    needed: float | None = None
    unit: str | None = None
    eta: str | None = None           # when an order would arrive
    options: list[FillAction] = []


def check_stock(rx: Prescription, inventory: SqliteInventory) -> StockCheck:
    open_fields = {e.field for e in rx.exceptions}
    unsettled = [n for n in REQUIRED if n not in rx.fields or rx.fields[n].decision not in _RELIABLE or n in open_fields]
    if unsettled:
        names = ", ".join(unsettled)
        return StockCheck(status=StockStatus.NOT_CHECKED,
                          message=f"Stock is checked once the {names} {'is' if len(unsettled) == 1 else 'are'} settled.")

    drug, strength, quantity = (_value(rx, n) for n in REQUIRED)
    form = _value(rx, "form")
    matches = inventory.find(drug, strength, form) or (inventory.find(drug, strength) if form else [])
    if len(matches) != 1:
        if len(matches) > 1:
            return StockCheck(status=StockStatus.NOT_CHECKED, message=f"More than one {drug} {strength} product; check the form.")
        return StockCheck(status=StockStatus.NOT_STOCKED, message=f"This pharmacy doesn't stock {drug} {strength}.",
                          eta=SPECIAL_ORDER_ETA, options=OPTIONS[StockStatus.NOT_STOCKED])
    product = matches[0]

    needed = _needed(quantity, product)
    if needed is None:
        return StockCheck(status=StockStatus.NOT_CHECKED, **_about(product),
                          message=f"The quantity {quantity!r} can't be compared with stock counted in {product.unit}.")
    status = (StockStatus.IN_STOCK if product.on_hand >= needed
              else StockStatus.OUT_OF_STOCK if product.on_hand <= 0 else StockStatus.PARTIAL)
    message = {
        StockStatus.IN_STOCK: f"{_n(product.on_hand)} {product.unit} on hand; {_n(needed)} needed.",
        StockStatus.PARTIAL: f"Only {_n(product.on_hand)} of {_n(needed)} {product.unit} in stock.",
        StockStatus.OUT_OF_STOCK: f"Out of stock. An order would arrive {product.supplier_eta}.",
    }[status]
    return StockCheck(status=status, message=message, needed=needed, eta=product.supplier_eta,
                      options=OPTIONS[status], **_about(product))


def _about(product: Product) -> dict:
    return {"product_id": product.product_id, "product": f"{product.drug} {product.strength} {product.form}",
            "location": product.location, "on_hand": product.on_hand, "unit": product.unit}


def _needed(quantity: str, product: Product) -> float | None:
    """'#30' -> 30 tablets; '300 mL' -> 300 mL; None when the units don't fit the product."""
    match = _QUANTITY_RE.match(quantity.strip())
    if not match:
        return None
    amount, unit = float(match.group(1)), (match.group(2) or "").casefold()
    if product.unit.casefold() == "ml":
        return amount if unit == "ml" else None
    return amount if unit in _COUNT_UNITS or unit == "" else None


def _value(rx: Prescription, name: str) -> str | None:
    field = rx.fields.get(name)
    value = (field.normalized_value or field_value(field)) if field else None
    return value.strip() if value and value.strip() else None


def _n(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"
