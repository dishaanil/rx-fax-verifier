"""Stock lookup and fulfillment: information for the pharmacist, never part of approval."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.inventory import FulfillmentService, InventoryError, SqliteInventory, StockStatus, check_stock
from backend.main import create_app
from backend.models import PrescriptionStatus
from backend.review import ConflictError, DomainError, ReviewService
from backend.storage import MemoryStore
from backend.tests.conftest import fixed_clock, processed


def _inventory(tmp_path, on_hand=900, unit="tablets", strength="10 mg", form="tablet", drug="Lisinopril"):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"products": [
        {"drug": drug, "strength": strength, "form": form, "unit": unit, "on_hand": on_hand,
         "location": "Aisle 2, Bay A, Shelf 2", "supplier_eta": "tomorrow by 10 am"},
    ]}))
    return SqliteInventory(path)


def _rx(quantity="30", **fields):
    rx = processed("rx_A")
    rx.fields["quantity"].raw_value = quantity
    rx.fields["quantity"].normalized_value = quantity
    for name, value in fields.items():
        rx.fields[name].normalized_value = value
    return rx


# --- the demo database ----------------------------------------------------


def test_demo_inventory_matches_how_faxes_are_written():
    inv = SqliteInventory()
    assert [p.location for p in inv.find("metoprolol tartrate", "75mg", "tab")] == ["Aisle 3, Bay B, Shelf 2"]
    assert inv.find("Hydroxyzine hydrochloride", "25 mg", "Tablets")[0].on_hand == 12
    assert inv.find("Amoxicillin", "250 mg/5 mL", "susp")[0].unit == "mL"
    assert inv.find("amoxicillin suspension", "250mg/5ml")[0].form == "suspension"
    # Strength and salt matter: 15 mg isn't stocked, and succinate is not tartrate.
    assert inv.find("metoprolol tartrate", "15 mg") == []
    assert inv.find("metoprolol succinate", "75 mg") == []


def test_dispense_never_goes_below_zero(tmp_path):
    inv = _inventory(tmp_path, on_hand=10)
    product = inv.find("lisinopril", "10 mg")[0]
    assert inv.dispense(product.product_id, 4).on_hand == 6
    with pytest.raises(InventoryError):
        inv.dispense(product.product_id, 7)
    assert inv.get(product.product_id).on_hand == 6


# --- stock check ----------------------------------------------------------


@pytest.mark.parametrize(("on_hand", "status", "options"), [
    (900, StockStatus.IN_STOCK, ["FILL"]),
    (12, StockStatus.PARTIAL, ["PARTIAL_FILL", "ORDER", "TRANSFER"]),
    (0, StockStatus.OUT_OF_STOCK, ["ORDER", "TRANSFER"]),
])
def test_stock_status_and_options(tmp_path, on_hand, status, options):
    check = check_stock(_rx("#30"), _inventory(tmp_path, on_hand=on_hand))
    assert check.status is status
    assert [o.value for o in check.options] == options
    assert (check.needed, check.location) == (30, "Aisle 2, Bay A, Shelf 2")


def test_not_stocked_offers_order_or_transfer(tmp_path):
    check = check_stock(_rx(strength="40 mg"), _inventory(tmp_path))
    assert check.status is StockStatus.NOT_STOCKED
    assert [o.value for o in check.options] == ["ORDER", "TRANSFER"]
    assert "special order" in check.eta


def test_never_looks_up_an_unsettled_value(tmp_path):
    """rx_037's drug is ambiguous and its quantity conflicts: no lookup on a possible misread."""
    check = check_stock(processed("rx_037"), _inventory(tmp_path))
    assert check.status is StockStatus.NOT_CHECKED
    assert "drug, quantity" in check.message
    assert check.options == []


def test_quantity_units_must_fit_the_product(tmp_path):
    inv = _inventory(tmp_path, unit="mL", strength="250 mg/5 mL", form="suspension", drug="Amoxicillin", on_hand=600)
    rx = _rx("300 mL", drug="amoxicillin", strength="250 mg/5 mL")
    rx.fields["form"] = rx.fields["drug"].model_copy(update={"raw_value": "susp", "normalized_value": "susp"})
    assert check_stock(rx, inv).needed == 300
    assert check_stock(_rx("#30", drug="amoxicillin", strength="250 mg/5 mL"), inv).status is StockStatus.NOT_CHECKED


# --- fulfillment ----------------------------------------------------------


@pytest.fixture
def store():
    s = MemoryStore()
    s.save(processed("rx_A"))
    return s


def _approved(store):
    ReviewService(store, clock=fixed_clock).approve("rx_A")


def test_fill_only_after_approval_and_only_once(store, tmp_path):
    inv = _inventory(tmp_path, on_hand=100)
    service = FulfillmentService(store, inv, clock=fixed_clock)
    with pytest.raises(ConflictError, match="approved"):
        service.fulfill("rx_A", "FILL")

    _approved(store)
    rx = service.fulfill("rx_A", "FILL")
    assert rx.status is PrescriptionStatus.APPROVED  # filling never changes approval
    assert rx.fulfillment["action"] == "FILL"
    assert (rx.fulfillment["dispensed"], rx.fulfillment["owed"]) == (30, 0)
    assert rx.fulfillment["location"] == "Aisle 2, Bay A, Shelf 2"
    assert inv.find("lisinopril", "10 mg")[0].on_hand == 70
    assert rx.audit_events[-1]["event"] == "PRESCRIPTION_FILLED"
    with pytest.raises(ConflictError, match="already"):
        service.fulfill("rx_A", "FILL")


def test_partial_fill_records_what_is_owed(store, tmp_path):
    inv = _inventory(tmp_path, on_hand=12)
    _approved(store)
    rx = FulfillmentService(store, inv, clock=fixed_clock).fulfill("rx_A", "PARTIAL_FILL")
    assert (rx.fulfillment["dispensed"], rx.fulfillment["owed"], rx.fulfillment["eta"]) == (12, 18, "tomorrow by 10 am")
    assert inv.find("lisinopril", "10 mg")[0].on_hand == 0


@pytest.mark.parametrize(("action", "pharmacy", "expected"), [
    ("ORDER", None, {"eta": "tomorrow by 10 am", "pharmacy": None}),
    ("TRANSFER", "Main St Pharmacy", {"eta": None, "pharmacy": "Main St Pharmacy"}),
    ("TRANSFER", "  ", {"pharmacy": "another pharmacy"}),
])
def test_out_of_stock_order_or_transfer(store, tmp_path, action, pharmacy, expected):
    _approved(store)
    rx = FulfillmentService(store, _inventory(tmp_path, on_hand=0), clock=fixed_clock).fulfill("rx_A", action, pharmacy)
    assert {k: rx.fulfillment[k] for k in expected} == expected
    assert rx.fulfillment["dispensed"] == 0


def test_only_the_options_the_stock_allows(store, tmp_path):
    _approved(store)
    service = FulfillmentService(store, _inventory(tmp_path, on_hand=0), clock=fixed_clock)
    with pytest.raises(ConflictError):
        service.fulfill("rx_A", "FILL")       # nothing on the shelf
    with pytest.raises(DomainError):
        service.fulfill("rx_A", "REJECT")     # stock never rejects a prescription


# --- API ------------------------------------------------------------------


def test_stock_and_fulfill_endpoints(store, tmp_path):
    inv = _inventory(tmp_path, on_hand=12)
    with TestClient(create_app(store=store, upload_dir=tmp_path, inventory=inv)) as client:
        stock = client.get("/api/prescriptions/rx_A/stock").json()
        assert (stock["status"], stock["options"]) == ("PARTIAL", ["PARTIAL_FILL", "ORDER", "TRANSFER"])
        assert client.post("/api/prescriptions/rx_A/fulfill", json={"action": "ORDER"}).status_code == 409

        assert client.post("/api/prescriptions/rx_A/approve").status_code == 200
        filled = client.post("/api/prescriptions/rx_A/fulfill", json={"action": "PARTIAL_FILL"})
        assert filled.status_code == 200, filled.text
        assert filled.json()["fulfillment"]["owed"] == 18
        assert client.get("/api/prescriptions/nope/stock").status_code == 404
