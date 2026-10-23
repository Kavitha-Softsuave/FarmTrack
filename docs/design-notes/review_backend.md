# BACKEND-REVIEW (19 Oct 2026): findings, decisions, needs a human

Short bullets; only real findings and decisions. Tests named here live under `backend/tests/`.

## Decisions taken (no questions asked)
- Another agent edited the same backend files at the same time (probe tests in `tests/_probe`, ENV check in `config.py`, `app_version` clamp in `devices.py`). I merged the two ENV validators into one (mine is the superset: `staging`, `uat`, `preprod` also read as prod) and kept my edits small and targeted.
- `Idempotency-Key` reused with DIFFERENT content still returns the first result (documented in OpenAPI). Rejecting it with 409 would make an offline-queue entry fail forever if the app regenerates a field (for example `sprayed_at`) on retry, and losing a spray-diary entry is worse than ignoring a changed body. The replay carries `Idempotent-Replayed: true` so a client can notice.
- `MISSING_HINDI_NAME` in `tests/services/test_crop_names.py` is empty: every crop a detector, the catalogue or the voice list can name now has a Devanagari draft name (`app/advice/crop_names.py`, one table for scan cards and advice text).

## Needs a human
- Hindi crop names added beyond the five demo crops and the voice list (banana, brinjal, okra, custard apple, ...) are my draft; native review please. `beans` stays `बीन्स` in the advice sentence (grammar) while the voice prompt says `फलियों`.
