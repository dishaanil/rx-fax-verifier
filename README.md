# RxBridge

RxBridge turns messy prescription inputs into verified structured drafts or precise human decisions.

> **The model proposes. Evidence and policy determine what can proceed.**

## Design

[`DESIGN.md`](DESIGN.md) is the **frozen** design specification. Build from it only, and don't edit it without agreement from the whole team.

## Contract

[`fixtures/rx_037.json`](fixtures/rx_037.json) is the **single source of truth for data shape**. The backend, frontend, extraction and test data all conform to it.

**Nobody renames a key without telling the backend owner first.**

## Ownership

| Owner | Area |
|---|---|
| Karthik | Backend, verification, policy |
| Disha | Extraction, test data |
| Noah | React UI, PRISM, submission |

## Structure

### Frontend development

Run `npm install` and `npm run dev` from `frontend/`. Vite proxies `/api`,
`/faxes`, and `/processed` to FastAPI at `http://127.0.0.1:8000`.
For a different backend, set `VITE_API_BASE_URL` before starting or building Vite;
that backend must allow the frontend origin via CORS and serve source images.

When the API is unavailable, the queue displays the contract fixture as a labeled,
read-only preview. Uploads never fall back to example data. The original fixture
image is not included, so its viewer reports that the source image is unavailable.

Frontend integration expects:

- `POST /api/intake`: multipart form field `file`, returning the full prescription
  contract (including a `PROCESSING` status for asynchronous extraction).
- `GET /api/prescriptions`: an array of full prescriptions or queue summaries
  containing `prescription_id`; summaries are hydrated through the detail endpoint.
- `GET /api/prescriptions/{id}`: the full current contract, also polled during processing.
- `POST /api/exceptions/{id}/resolve`: `{action: "SELECT_VALUE", value}` for
  confirmation/correction or `{action: "MARK_UNREADABLE"}`. The UI fetches the
  prescription again after successful revalidation.
- `POST /api/prescriptions/{id}/approve`: explicit pharmacist approval, followed
  by a fresh prescription read. Backend must enforce readiness and pharmacist authority.

Mutation responses accept JSON or HTTP 204. Request clarification and reject open
local draft forms; drafts do not contact a prescriber or change prescription status,
and are cleared when the review screen is left. Submission awaits defined backend
contracts. The review screen displays recorded resolutions, clarifications, reviewer
identity, and audit events. Source highlighting and crops
use pixel bounding boxes on the original, single-page image; multipage viewing
needs page-specific image URLs.

### Backend data still needed

The UI is connector-ready but deliberately does not call PRISM from the browser.
The backend owns PRISM and should append asynchronous `audit_events` to the
prescription response. Every event needs `ts`, `actor`, `event`, and a concise
`detail`; an optional primitive-only `data` map can carry identifiers. The UI
will display these events without letting them alter prescription status:

- `PRISM_TRACE_RECORDED`: `data.session_id` must equal `prescription_id`, with
  `data.step` set to `extract_primary`, `extract_secondary`, or `normalize_sig`.
- `PRISM_GUARDRAIL_FLAGGED`: detail must state the untrusted extracted text was
  flagged; policy—not PRISM or the UI—remains responsible for routing.
- `PRISM_EVALUATOR_COMPLETED`: detail must state the independent evaluation
  result. It is evidence only and must not delay the live route.

For the image viewer, `source.original_path` must resolve to the original image
bytes, and each field/exception bbox must use that image's pixel coordinate
system. The current viewer supports page 1; provide page-specific image URLs
before sending multi-page documents to the review workspace.

```
backend/
  main.py
  models/          preprocessing/   extraction/
  normalization/   references/      validators/
  policy/          review/          prism/
  storage/
frontend/
  src/pages/
  src/components/
fixtures/
  rx_037.json      # contract fixture
```

## Backend

Requires **Python 3.11**.

```bash
uv venv --python 3.11 .venv          # or: python3.11 -m venv .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
.venv/bin/python -m pytest            # offline; no network or model calls
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

| Variable | Default | Meaning |
|---|---|---|
| `RXBRIDGE_EXTRACTOR` | `stub` | `stub` maps the upload's filename stem to `fixtures/raw_<stem>.json` (`rx_037`, `rx_A`, `rx_C`, `rx_D`, `rx_E`, `rx_F`). `nicrron` runs the real extractor (`backend/extraction/nicrron.py`): needs `NICRRON_API_KEY`, `NICRRON_BASE_URL` and the two model names in `.env` (see `.env.example`). |
| `RXBRIDGE_SEED` | `0` | `1` loads the six demo fixtures into the in-memory store at startup. |
| `RXBRIDGE_UPLOAD_DIR` | `backend/uploads` | Where uploaded source files are saved (gitignored). |

State is in memory and is lost on restart.

### Endpoints

| Method | Path | Does |
|---|---|---|
| `POST` | `/api/intake` | Multipart `file`. SHA-256 → save → extract → validate → route. Extractor failure yields `UNPROCESSABLE`. |
| `GET` | `/api/prescriptions` | Queue: `prescription_id`, `patient`, `status`, `unresolved_count`, `received_at`. |
| `GET` | `/api/prescriptions/{id}` | Full canonical `Prescription`. |
| `POST` | `/api/exceptions/{exception_id}/resolve` | `{"action": ..., "value": ...}`; actions `CONFIRM`, `CORRECT`, `SELECT_VALUE`, `MARK_UNREADABLE`, `REQUEST_CLARIFICATION`, `REJECT`. Always revalidates. |
| `POST` | `/api/prescriptions/{id}/approve` | Pharmacist approval; only from `READY_FOR_VERIFICATION`, else 409. |
| `POST` | `/api/prescriptions/{id}/reject` | Rejects; 409 if already approved. |
| `GET` | `/api/prescriptions/{id}/source` | The uploaded source file, or 404. |

## Invariants

1. No critical field without source evidence may be `VERIFIED`.
2. No unresolved critical exception may coexist with `READY_FOR_VERIFICATION`.
3. Only an explicit pharmacist action may create `APPROVED`.
4. AI output never overwrites source truth.
5. Human correction preserves previous reads and signals.
6. Reference-data failure cannot turn `UNKNOWN` into `VALID`.
7. Reference-data failure cannot turn `UNKNOWN` into `INVALID`.
8. Normalization cannot silently alter critical meaning.
9. External clarification proposes evidence; it never approves or changes the order.
10. Resolving an exception always triggers revalidation.
11. Fields belonging to incompatible patient identities are never merged automatically.
12. Unreadable evidence never becomes `VERIFIED` because a model produced a plausible value.
