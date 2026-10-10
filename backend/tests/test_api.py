import pytest
from fastapi.testclient import TestClient

from backend.main import create_app, seed
from backend.models import Prescription
from backend.storage import MemoryStore

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store, tmp_path, monkeypatch):
    monkeypatch.setenv("RXBRIDGE_EXTRACTOR", "stub")
    monkeypatch.delenv("RXBRIDGE_SEED", raising=False)
    with TestClient(create_app(store=store, upload_dir=tmp_path)) as c:
        yield c


def upload(client, name="rx_037.png", data=PNG):
    response = client.post("/api/intake", files={"file": (name, data, "image/png")})
    assert response.status_code == 200, response.text
    return response.json()


def exception_of(rx, exc_type):
    return next(e for e in rx["exceptions"] if e["type"] == exc_type)


def test_import_does_not_seed(monkeypatch):
    monkeypatch.setenv("RXBRIDGE_SEED", "0")
    with TestClient(create_app(store=MemoryStore())) as c:
        assert c.get("/api/prescriptions").json() == []


def test_seed_on_startup(monkeypatch):
    monkeypatch.setenv("RXBRIDGE_SEED", "1")
    with TestClient(create_app(store=MemoryStore())) as c:
        ids = {r["prescription_id"] for r in c.get("/api/prescriptions").json()}
    assert ids == {"rx_037", "rx_A", "rx_C", "rx_D", "rx_E", "rx_F"}


def test_intake_returns_canonical_prescription(client, tmp_path):
    rx = upload(client)

    Prescription.model_validate(rx)
    assert rx["prescription_id"] == "rx_037"
    assert rx["status"] == "REVIEW_REQUIRED"
    assert [e["type"] for e in rx["exceptions"]] == ["AMBIGUOUS_DRUG", "POSSIBLE_QUANTITY_CONFLICT"]
    assert rx["source"]["original_path"] == str((tmp_path / "rx_037" / "rx_037.png").resolve())
    assert (tmp_path / "rx_037" / "rx_037.png").read_bytes() == PNG
    assert len(rx["source"]["sha256"]) == 64


def test_intake_unknown_document_is_unprocessable(client):
    rx = upload(client, "mystery.png")

    assert rx["status"] == "UNPROCESSABLE"
    assert rx["fields"] == {}
    assert client.get(f"/api/prescriptions/{rx['prescription_id']}").json()["status"] == "UNPROCESSABLE"


def test_intake_sanitizes_filename(client, tmp_path):
    rx = upload(client, "../../etc/rx_A.png")

    assert rx["prescription_id"] == "rx_A"
    assert rx["source"]["original_path"].startswith(str(tmp_path.resolve()))


def test_duplicate_upload_gets_new_id_and_duplicate_exception(client, store):
    first = upload(client, "rx_A.png")
    second = upload(client, "rx_A.png")

    assert first["prescription_id"] == "rx_A"
    assert second["prescription_id"] == "rx_A_2"
    assert client.get("/api/prescriptions/rx_A").json() == first
    dup = second["exceptions"][0]
    assert (dup["type"], dup["field"], dup["severity"]) == ("DUPLICATE_DOCUMENT", "document", "CRITICAL")
    assert second["status"] == "REVIEW_REQUIRED"
    assert dup["exception_id"] == "rx_A_2__exc_01"

    rx, exc = store.find_exception(dup["exception_id"])
    assert rx.prescription_id == "rx_A_2"

    assert client.post("/api/prescriptions/rx_A_2/approve").status_code == 409
    for action in ("CONFIRM", "CORRECT", "SELECT_VALUE", "MARK_UNREADABLE", "REQUEST_CLARIFICATION"):
        r = client.post(f"/api/exceptions/{dup['exception_id']}/resolve", json={"action": action, "value": "x"})
        assert r.status_code == 400, action
    r = client.post(f"/api/exceptions/{dup['exception_id']}/resolve", json={"action": "REJECT"})
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"


def test_find_exception_distinguishes_same_fixture_uploads(client, store):
    a = upload(client, "rx_037.png", b"one")
    b = upload(client, "rx_037.png", b"two")

    for rx in (a, b):
        for exc in rx["exceptions"]:
            found, _ = store.find_exception(exc["exception_id"])
            assert found.prescription_id == rx["prescription_id"]


def test_queue_summaries(client):
    upload(client, "rx_037.png", b"1")
    upload(client, "rx_A.png", b"2")

    queue = {r["prescription_id"]: r for r in client.get("/api/prescriptions").json()}

    assert queue["rx_037"]["patient"] == "James Peterson"
    assert queue["rx_037"]["status"] == "REVIEW_REQUIRED"
    assert queue["rx_037"]["unresolved_count"] == 2
    assert queue["rx_A"]["unresolved_count"] == 0
    assert queue["rx_A"]["status"] == "READY_FOR_VERIFICATION"
    assert queue["rx_A"]["received_at"].endswith("Z")
    assert set(queue["rx_A"]) == {"prescription_id", "patient", "status", "unresolved_count", "received_at"}


def test_get_missing_prescription_404(client):
    assert client.get("/api/prescriptions/nope").status_code == 404


def test_api_approval_loop(client):
    rx = upload(client)
    assert client.post("/api/prescriptions/rx_037/approve").status_code == 409

    drug = exception_of(rx, "AMBIGUOUS_DRUG")
    r = client.post(f"/api/exceptions/{drug['exception_id']}/resolve", json={"action": "CONFIRM"})
    assert r.status_code == 400
    assert drug["exception_id"] in [e["exception_id"] for e in client.get("/api/prescriptions/rx_037").json()["exceptions"]]

    r = client.post(f"/api/exceptions/{drug['exception_id']}/resolve", json={"action": "SELECT_VALUE", "value": "hydroxyzine HCl"})
    assert r.status_code == 200
    qty = exception_of(rx, "POSSIBLE_QUANTITY_CONFLICT")
    r = client.post(f"/api/exceptions/{qty['exception_id']}/resolve", json={"action": "CONFIRM"})
    assert r.json()["status"] == "READY_FOR_VERIFICATION"
    assert r.json()["fields"]["quantity"]["raw_value"] == "30"

    r = client.post("/api/prescriptions/rx_037/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"
    assert r.json()["approved_by"] == "Demo Pharmacist"

    assert client.post("/api/prescriptions/rx_037/reject").status_code == 409
    assert client.get("/api/prescriptions/rx_037").json()["status"] == "APPROVED"


@pytest.mark.parametrize(
    "body",
    [{"action": "APPROVE"}, {"action": "SELECT_VALUE", "value": "not-a-candidate"}, {"action": "CORRECT", "value": ""}, {}, {"value": "x"}, {"action": "CORRECT", "value": "x", "extra": 1}],
)
def test_resolve_bad_request_400(client, body):
    rx = upload(client)
    exc = exception_of(rx, "AMBIGUOUS_DRUG")

    assert client.post(f"/api/exceptions/{exc['exception_id']}/resolve", json=body).status_code == 400


def test_resolve_missing_exception_404(client):
    assert client.post("/api/exceptions/nope/resolve", json={"action": "CONFIRM"}).status_code == 404


def test_resolve_on_rejected_409(client):
    rx = upload(client)
    client.post("/api/prescriptions/rx_037/reject")
    exc = exception_of(rx, "AMBIGUOUS_DRUG")

    r = client.post(f"/api/exceptions/{exc['exception_id']}/resolve", json={"action": "SELECT_VALUE", "value": "hydroxyzine HCl"})
    assert r.status_code == 409


def test_reject_endpoint(client):
    upload(client)

    r = client.post("/api/prescriptions/rx_037/reject")

    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"
    assert r.json()["audit_events"][-1]["event"] == "PRESCRIPTION_REJECTED"
    assert client.post("/api/prescriptions/rx_037/reject").status_code == 200
    assert client.post("/api/prescriptions/nope/reject").status_code == 404


def test_reject_approved_409(client):
    upload(client, "rx_A.png")
    assert client.post("/api/prescriptions/rx_A/approve").status_code == 200

    assert client.post("/api/prescriptions/rx_A/reject").status_code == 409


def test_approve_missing_404(client):
    assert client.post("/api/prescriptions/nope/approve").status_code == 404


def test_source_endpoint_serves_uploaded_file(client):
    upload(client)

    r = client.get("/api/prescriptions/rx_037/source")

    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"


def test_source_missing_prescription_404(client):
    r = client.get("/api/prescriptions/nope/source")

    assert r.status_code == 404
    assert "detail" in r.json()


def test_source_missing_original_path_404(client, store):
    upload(client)
    rx = store.get("rx_037")
    rx.source.pop("original_path")
    store.save(rx)

    assert client.get("/api/prescriptions/rx_037/source").status_code == 404


def test_source_file_deleted_404(client, tmp_path):
    upload(client)
    (tmp_path / "rx_037" / "rx_037.png").unlink()

    assert client.get("/api/prescriptions/rx_037/source").status_code == 404


def test_source_outside_upload_dir_404(client, store, tmp_path):
    upload(client)
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret")
    rx = store.get("rx_037")
    rx.source["original_path"] = str(outside)
    store.save(rx)

    assert client.get("/api/prescriptions/rx_037/source").status_code == 404


def test_seeded_record_without_file_does_not_crash(store, tmp_path):
    seed(store)
    with TestClient(create_app(store=store, upload_dir=tmp_path)) as c:
        r = c.get("/api/prescriptions/rx_037/source")
    assert r.status_code == 404


def test_cors_allows_vite_dev_server(client):
    r = client.options(
        "/api/prescriptions",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_injection_upload_never_approved(client):
    rx = upload(client, "rx_F.png")

    assert rx["status"] == "REVIEW_REQUIRED"
    assert client.post("/api/prescriptions/rx_F/approve").status_code == 409
    assert client.get("/api/prescriptions/rx_F").json()["approved_by"] is None
