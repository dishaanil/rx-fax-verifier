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
| `RXBRIDGE_EXTRACTOR` | `stub` | `stub` maps the upload's filename stem to `fixtures/raw_<stem>.json` (`rx_037`, `rx_A`, `rx_C`, `rx_D`, `rx_E`, `rx_F`). `nicrron` is reserved for the real extractor. |
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
