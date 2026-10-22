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
| `GOOGLE_VISION_API_KEY` | unset | Optional, `nicrron` only. Google Cloud Vision OCR finds where each value is written, so the highlight box lands on the right text (`backend/extraction/locate.py`). Unset, or if a value is not found, the model's estimated box is used. |
| `RXBRIDGE_CALLER` | `simulated` | Who places "Call prescriber" calls. `simulated`: a scripted assistant talks to a model playing the prescriber; nothing is dialled and ElevenLabs is never contacted. `elevenlabs`: real calls (see below). |
| `RXBRIDGE_SEED` | `0` | `1` loads the six demo fixtures into the in-memory store at startup. |
| `RXBRIDGE_UPLOAD_DIR` | `backend/uploads` | Where uploaded source files are saved (gitignored). |

State is in memory and is lost on restart.

### Endpoints

| Method | Path | Does |
|---|---|---|
| `POST` | `/api/intake` | Multipart `file`. SHA-256 → save → extract → validate → route. Extractor failure yields `UNPROCESSABLE`. |
| `GET` | `/api/prescriptions` | Queue: `prescription_id`, `patient`, `status`, `unresolved_count`, `received_at`. |
| `GET` | `/api/prescriptions/{id}` | Full canonical `Prescription`. |
| `POST` | `/api/exceptions/{exception_id}/resolve` | `{"action": ..., "value": ...}`; actions `CONFIRM`, `CORRECT`, `SELECT_VALUE`, `MARK_UNREADABLE`, `REQUEST_CLARIFICATION`, `USE_PRESCRIBER_ANSWER`, `REJECT`. Always revalidates. |
| `POST` | `/api/exceptions/{exception_id}/call` | Calls the prescriber about this exception. Returns at once with the call `CALLING`; the result (`ANSWERED`, `UNCLEAR` or `FAILED`, with the transcript) appears in `clarifications` when the call ends. |
| `POST` | `/api/prescriptions/{id}/approve` | Pharmacist approval; only from `READY_FOR_VERIFICATION`, else 409. |
| `POST` | `/api/prescriptions/{id}/reject` | Rejects; 409 if already approved. |
| `GET` | `/api/prescriptions/{id}/stock` | Shelf stock for the verified drug, strength and quantity: status, location, on hand, needed, and the fill options it allows. Information only. |
| `POST` | `/api/prescriptions/{id}/fulfill` | After approval: `{"action": "FILL" \| "PARTIAL_FILL" \| "ORDER" \| "TRANSFER", "pharmacy": ...}`. Only the options the stock allows; one decision per prescription. |
| `GET` | `/api/prescriptions/{id}/source` | The uploaded source file, or 404. |

### Call prescriber

When an issue can't be settled from the fax, the pharmacist can have an AI assistant call the prescriber
(`backend/calls/`). The number is the prescriber's office phone read from the fax (`prescriber_phone`, an
optional field that never blocks approval).

- The assistant says it is an AI, identifies the patient, asks one open question ("What strength did you
  prescribe?") and never suggests the value that was read. It only mentions other values, such as the drug,
  once they are verified. It reads the answer back and asks the prescriber to confirm.
- A confirmed answer is shown as evidence ("Dr. Walker said 75 mg") with the transcript. It is applied
  only when the pharmacist clicks "Use 75 mg" (`USE_PRESCRIBER_ANSWER`), and the field's resolution records
  the call. If there is no clear answer, the pharmacist chooses a value, calls the prescriber themselves, or
  rejects.
- If the prescriber corrects something else on the call ("her date of birth is November 6, not January 6"),
  the assistant acknowledges it and that field gets its own issue (`PRESCRIBER_CORRECTION`) with both values,
  so approval stays blocked until the pharmacist decides. Nothing is changed automatically.
- **The demo uses `RXBRIDGE_CALLER=simulated`** (the default). A model plays the prescriber, answering from
  the demo faxes' ground truth (`backend/calls/charts.py`, which only the simulation may import). For any
  other upload it has no chart and defers, which shows the "couldn't clarify" path. The model calls go
  through the Nicrron gateway and are traced in PRISM.
- `backend/calls/elevenlabs.py` places real calls through an ElevenLabs agent (outbound call, then the
  transcript and the agent's data-collection results). It is off unless `RXBRIDGE_CALLER=elevenlabs`, refuses
  any number not in `RXBRIDGE_CALL_ALLOWLIST`, and has not yet been run against the live API. Before calling
  real prescribers: check the number against the NPI Registry (a forged fax can list a fake number), have a
  BAA with ElevenLabs, and follow call-recording consent rules.

### Stock and fill

Once the drug, strength and quantity are verified (or set by the pharmacist), RxBridge looks the product up
in the pharmacy's stock (`backend/inventory/`) and shows where it is on the shelf. It never looks up a value
that is still in question, so a misread can't show false stock or send someone to the wrong shelf.

- **Before approval** the final check shows the stock (in stock, not enough, out of stock, not stocked here).
  It is information only and never affects approval.
- **After approval** a fourth step, **Fill**, offers only what the stock allows: *Mark filled* when there is
  enough; *Fill what's there and owe the rest*, *Order it* or *Send to another pharmacy* when there isn't.
  Stock never rejects a prescription: a valid order that is out of stock is still valid.
- **Demo data:** `fixtures/inventory.json`, loaded into an in-memory SQLite database at startup (fills reset
  on restart). Matching is by drug, strength and form after normalisation, so "Metoprolol Tartrate 75mg tab"
  finds the 75 mg tablets, never the 25 mg. Set up for the demos: A atorvastatin in stock, B metoprolol 75 mg
  in stock, C amoxicillin 250 mg/5 mL out of stock, D hydroxyzine 25 mg only 12 tablets. A real pharmacy
  system or hosted database would replace `SqliteInventory` behind the same `find` / `get` / `dispense`.

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
