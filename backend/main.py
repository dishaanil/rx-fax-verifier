"""RxBridge FastAPI app: ten routes over the deterministic pipeline.

Run: uvicorn backend.main:app --reload --port 8000
Importing this module creates an empty app; seeding happens only at startup
when RXBRIDGE_SEED=1.
"""

import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.calls import Caller, CallError, CallRequest, CallResult, calls_are_simulated, get_caller
from backend.extraction import ExtractionProvider, get_extractor
from backend.extraction.stub import FIXTURES_DIR, STUB_IDS, StubExtractor
from backend.intake import intake
from backend.inventory import FulfillmentService, SqliteInventory, StockCheck
from backend.models import Prescription, PrescriptionStatus
from backend.review import ConflictError, DomainError, NotFoundError, ReviewService
from backend.storage import MemoryStore

DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"

log = logging.getLogger(__name__)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    value: str | None = None


class FulfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    pharmacy: str | None = None


class QueueItem(BaseModel):
    prescription_id: str
    patient: str | None
    status: PrescriptionStatus
    unresolved_count: int
    received_at: str | None


def seed(store: MemoryStore) -> None:
    """Load the demo raw fixtures through the normal intake path (no files written)."""
    for pid in STUB_IDS:
        data = (FIXTURES_DIR / f"raw_{pid}.json").read_bytes()
        intake(store, StubExtractor, f"{pid}.png", data, upload_dir=None)


def create_app(
    store: MemoryStore | None = None,
    upload_dir: Path | None = None,
    extractor_factory: Callable[[], ExtractionProvider] = get_extractor,
    caller_factory: Callable[[], Caller] = get_caller,
    inventory: SqliteInventory | None = None,
) -> FastAPI:
    store = store or MemoryStore()
    upload_dir = (upload_dir or Path(os.environ.get("RXBRIDGE_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))).resolve()
    review = ReviewService(store)
    fulfillment = FulfillmentService(store, inventory or SqliteInventory())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if os.environ.get("RXBRIDGE_SEED", "0") == "1":
            seed(store)
        yield

    app = FastAPI(title="RxBridge", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": jsonable_errors(exc)})

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.post("/api/intake", response_model=Prescription)
    def post_intake(file: UploadFile) -> Prescription:
        # Sync handler: FastAPI runs it in its threadpool, so a slow extraction never blocks the event loop.
        data = file.file.read()
        return intake(store, extractor_factory, file.filename, data, upload_dir)

    @app.get("/api/prescriptions", response_model=list[QueueItem])
    def list_prescriptions() -> list[QueueItem]:
        return [_summary(rx) for rx in store.list()]

    @app.get("/api/prescriptions/{prescription_id}", response_model=Prescription)
    def get_prescription(prescription_id: str) -> Prescription:
        rx = store.get(prescription_id)
        if rx is None:
            raise NotFoundError(f"No prescription {prescription_id!r}.")
        return rx

    @app.post("/api/exceptions/{exception_id}/resolve", response_model=Prescription)
    def resolve_exception(exception_id: str, body: ResolveRequest) -> Prescription:
        return review.resolve(exception_id, body.action, body.value)

    @app.post("/api/exceptions/{exception_id}/call", response_model=Prescription)
    def call_prescriber(exception_id: str, tasks: BackgroundTasks) -> Prescription:
        """Start a call to the prescriber about one exception. Returns at once with the call CALLING;
        the result is recorded when the call ends (poll the prescription)."""
        rx, request = review.start_call(exception_id, simulated=calls_are_simulated())
        tasks.add_task(_run_call, review, caller_factory, request)
        return rx

    @app.post("/api/prescriptions/{prescription_id}/approve", response_model=Prescription)
    def approve(prescription_id: str) -> Prescription:
        return review.approve(prescription_id)

    @app.post("/api/prescriptions/{prescription_id}/reject", response_model=Prescription)
    def reject(prescription_id: str) -> Prescription:
        return review.reject(prescription_id)

    @app.get("/api/prescriptions/{prescription_id}/stock", response_model=StockCheck)
    def get_stock(prescription_id: str) -> StockCheck:
        """Shelf stock for the verified drug, strength and quantity. Information only: never affects approval."""
        return fulfillment.stock(prescription_id)

    @app.post("/api/prescriptions/{prescription_id}/fulfill", response_model=Prescription)
    def fulfill(prescription_id: str, body: FulfillRequest) -> Prescription:
        """After approval: FILL, PARTIAL_FILL, ORDER or TRANSFER, whichever the stock allows."""
        return fulfillment.fulfill(prescription_id, body.action, body.pharmacy)

    @app.get("/api/prescriptions/{prescription_id}/source")
    def get_source(prescription_id: str) -> FileResponse:
        rx = store.get(prescription_id)
        if rx is None:
            raise NotFoundError(f"No prescription {prescription_id!r}.")
        original = rx.source.get("original_path")
        if not original:
            raise NotFoundError("This prescription has no source file.")
        path = Path(original).resolve()
        # Only serve files intake saved; source paths from an extractor are untrusted.
        if not path.is_relative_to(upload_dir) or not path.is_file():
            raise NotFoundError("Source file not found.")
        return FileResponse(path)

    return app


def _run_call(review: ReviewService, caller_factory: Callable[[], Caller], request: CallRequest) -> None:
    """Runs after the response (FastAPI's threadpool). Any failure is recorded as FAILED, never lost."""
    try:
        result = caller_factory().place_call(request)
    except CallError as exc:
        result = CallResult("FAILED", None, str(exc))
    except Exception as exc:  # the call must always end in a recorded outcome
        log.exception("Prescriber call %s crashed", request.call_id)
        result = CallResult("FAILED", None, f"The call could not be completed: {exc}")
    review.finish_call(request.prescription_id, request.call_id, result)


def jsonable_errors(exc: RequestValidationError) -> list[dict]:
    return [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]


def _summary(rx: Prescription) -> QueueItem:
    patient = rx.fields.get("patient")
    received = next((e.get("ts") for e in rx.audit_events if e.get("event") == "DOCUMENT_RECEIVED"), None)
    return QueueItem(
        prescription_id=rx.prescription_id,
        patient=(patient.normalized_value or patient.raw_value) if patient else None,
        status=rx.status,
        unresolved_count=len(rx.exceptions),
        received_at=received,
    )


app = create_app()
