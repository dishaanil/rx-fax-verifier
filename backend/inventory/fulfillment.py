"""After approval: fill from the shelf, partially fill, order, or send to another pharmacy.

Fulfillment never changes approval: it runs only on an APPROVED prescription,
records one decision, and the pharmacist makes it. Stock never rejects a
prescription; a valid order that is out of stock is still valid.
"""

from backend.inventory.check import FillAction, StockStatus, check_stock
from backend.inventory.store import InventoryError, SqliteInventory
from backend.models import Prescription, PrescriptionStatus
from backend.pipeline import Clock, append_event, utc_now
from backend.review import ConflictError, DomainError, NotFoundError
from backend.review.service import DEMO_PHARMACIST
from backend.storage import MemoryStore

_EVENTS = {
    FillAction.FILL: "PRESCRIPTION_FILLED",
    FillAction.PARTIAL_FILL: "PRESCRIPTION_PARTIALLY_FILLED",
    FillAction.ORDER: "STOCK_ORDERED",
    FillAction.TRANSFER: "TRANSFER_REQUESTED",
}


class FulfillmentService:
    def __init__(self, store: MemoryStore, inventory: SqliteInventory, clock: Clock = utc_now) -> None:
        self.store = store
        self.inventory = inventory
        self.clock = clock

    def stock(self, prescription_id: str):
        return check_stock(self._get(prescription_id), self.inventory)

    def fulfill(self, prescription_id: str, action: str, pharmacy: str | None = None) -> Prescription:
        with self.store.lock:
            rx = self._get(prescription_id)
            if rx.status is not PrescriptionStatus.APPROVED:
                raise ConflictError("Only an approved prescription can be filled.")
            if rx.fulfillment is not None:
                raise ConflictError("This prescription already has a fill decision.")
            try:
                act = FillAction(action)
            except ValueError:
                raise DomainError(f"Unknown fill action {action!r}.") from None

            check = check_stock(rx, self.inventory)
            if act not in check.options:
                raise ConflictError(f"{act.value} isn't available: {check.message}")

            record = {
                "action": act.value, "product": check.product, "unit": check.unit, "location": check.location,
                "needed": check.needed, "dispensed": 0, "owed": 0, "eta": None, "pharmacy": None,
                "by": DEMO_PHARMACIST, "at": self.clock(),
            }
            if act in (FillAction.FILL, FillAction.PARTIAL_FILL):
                amount = check.needed if act is FillAction.FILL else check.on_hand
                try:
                    self.inventory.dispense(check.product_id, amount)
                except InventoryError:
                    raise ConflictError("Stock changed since it was checked; refresh and try again.") from None
                record.update(dispensed=amount, owed=(check.needed or 0) - amount)
                if act is FillAction.PARTIAL_FILL:
                    record["eta"] = check.eta  # the rest is ordered
            elif act is FillAction.ORDER:
                record["eta"] = check.eta
            else:
                record["pharmacy"] = (pharmacy or "").strip() or "another pharmacy"

            rx.fulfillment = record
            append_event(rx, self.clock, "PHARMACIST", _EVENTS[act], action=act.value,
                         stock_status=check.status.value)
            self.store.save(rx)
            return rx

    def _get(self, prescription_id: str) -> Prescription:
        rx = self.store.get(prescription_id)
        if rx is None:
            raise NotFoundError(f"No prescription {prescription_id!r}.")
        return rx


__all__ = ["FulfillmentService", "StockStatus"]
