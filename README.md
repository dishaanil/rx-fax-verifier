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
