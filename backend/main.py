"""RxBridge FastAPI app: seven routes over the deterministic pipeline.

Run: uvicorn backend.main:app --reload --port 8000
Importing this module creates an empty app; seeding happens only at startup
when RXBRIDGE_SEED=1.
"""

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.extraction import ExtractionProvider, get_extractor
from backend.extraction.stub import FIXTURES_DIR, STUB_IDS, StubExtractor
from backend.intake import intake
from backend.models import Prescription, PrescriptionStatus
from backend.review import ConflictError, DomainError, NotFoundError, ReviewService
from backend.storage import MemoryStore

DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    value: str | None = None


class QueueItem(BaseModel):
    prescription_id: str
    patient: str | None
    status: PrescriptionStatus
    unresolved_count: int
    received_at: str | None


def seed(store: MemoryStore) -> None:
    """Load the demo raw fixtures through the normal intake path (no files written)."""
    extractor = StubExtractor()
    for pid in STUB_IDS:
        data = (FIXTURES_DIR / f"raw_{pid}.json").read_bytes()
        intake(store, extractor, f"{pid}.png", data, upload_dir=None)


def create_app(
    store: MemoryStore | None = None,
    upload_dir: Path | None = None,
    extractor_factory: Callable[[], ExtractionProvider] = get_extractor,
) -> FastAPI:
    store = store or MemoryStore()
    upload_dir = (upload_dir or Path(os.environ.get("RXBRIDGE_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))).resolve()
    review = ReviewService(store)

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
    async def post_intake(file: UploadFile) -> Prescription:
        data = await file.read()
        return intake(store, extractor_factory(), file.filename, data, upload_dir)

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

    @app.post("/api/prescriptions/{prescription_id}/approve", response_model=Prescription)
    def approve(prescription_id: str) -> Prescription:
        return review.approve(prescription_id)

    @app.post("/api/prescriptions/{prescription_id}/reject", response_model=Prescription)
    def reject(prescription_id: str) -> Prescription:
        return review.reject(prescription_id)

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
