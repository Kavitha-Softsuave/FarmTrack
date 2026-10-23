# BACKEND-FIX: doubts and decisions (smoke-test defects, 19 Oct 2026)

Scope: the 8 items of the smoke-test brief. All contract changes are additive (see "OpenAPI diff"). Tests: `tests/api/test_spray_free_text_api.py`, `test_idempotency_api.py`, `tests/services/test_product_match.py`, `test_dev_schema_patch.py`, `tests/alerts/test_scan_link.py`, `tests/admin/test_expert_requests.py`, `tests/vision/test_hints.py`, `tests/test_ops_files.py` (+ additions to the existing spray, expert, migration, startup and real-provider tests).

## 1. "I sprayed this" tick
- `advice_id` only -> the advice's FIRST product (the one read aloud). Other products of the same advice: the app sends `product_id`. An advice without products (expert route) keeps 422 `spray_needs_product`.
- Decision: `advice_id` + typed `free_text` (no `product_id`) uses the typed name, not the advice default (the farmer typed something on purpose). Before, a single-product advice won over the text.
- `product_id` is not trusted: it must be one of the advice's products or in the product master, else 422 `unknown_product`. Doubt: an unknown id WITH a typed name is ignored and the name is used (an offline-queued entry must not be lost to a 422 forever). The advice must be the caller's (404 `advice_not_found`, also when only `advice_id` is sent).

## 2. Typed names -> catalogue (`app/services/product_match.py`)
- Exact identity only, after clean-up (case, punctuation, `%` strengths, trailing WP/EC/SC/units/numbers, Hindi nukta/chandrabindu/ZW joiners): product id, English or Hindi active name(s) (mixtures in any order, joined by + & and), brand names (product master `brand_example`, HP evaluated brands, HP brand table). "Mancozeb and zinc" is NOT matched (a known name inside other words is never guessed).
- Restricted to the entry's crop. Several rows of one identity are fine when they agree on category, FRAC code, ban status and waiting period (mancozeb: P005/P023/P050 -> lowest usable id P005). When they disagree (Ziram: P003/P042 have no waiting period, P043 has 21 days) or a brand means two ingredients -> ambiguous: `product_id` stays None.
- Not recognised or ambiguous -> saved as typed + yellow `PRODUCT_NOT_RECOGNISED` (EN + HI, no digits). Not added for nutrient text (zinc, boron ...): those are not pesticides (so "mancozeb + zinc" counts as a nutrient entry; the rules' same-day tank-mix check still applies).
- A brand match is named "Bavistin 50 WP (Carbendazim)" in `product_name` (what was typed + what it is); the Zoho record keeps the typed text as `trade_name`. An id/active match uses the master's active name.
- Sequence tested with the REAL rules: Myclobutanil (P012) then "mancozeb" the same day -> only `PROPOSED_BAN` (mancozeb is "proposed ban, still registered"). A second identical log within 5 minutes is treated by the rules as a duplicate (no repeat warning); the same chemical on another day gives `ROTATION_LIMIT` (same active). Dodine too close to harvest -> red `WAITING_PERIOD_EXCEEDS_HARVEST`.
- QUESTION FOR THE AGRONOMIST (no rule invented): the rules give NO warning for two different pesticides logged on the same day. HP point 7 forbids mixing others with the recommended product, but a diary cannot tell one tank from two. Should two different chemicals on one day produce a soft "if these were mixed in one tank, do not" warning? Also: the Ziram 27 % SC rows (P003, P042) have no waiting period in the data while the 80 % WP row has 21 days; please confirm.

## 3. Idempotency (`app/api/idempotency.py`)
- `Idempotency-Key` (8-80 chars of A-Za-z0-9 . _ : -, else 400 `invalid_idempotency_key`; blank = none) on `POST /v1/scans`, `/v1/spray-logs`, `/v1/expert-requests` (the only create routes). Stored in `client_request_id` (String 80) with a UNIQUE index (farmer_id, client_request_id) on `scans`, `spray_logs`, `expert_requests`; NULLs never collide. Migration 0001 edited in place.
- Replay by the same farmer: 200, same ids, header `Idempotent-Replayed: true`; no new row, no models, no composer, no Zoho write, no rate-limit hit. A scan replay returns the scan's CURRENT stored result (e.g. after the crop was confirmed), same ids. Another farmer with the same key does not collide. A key identifies the first request only (different content with the same key gets the first result; documented in OpenAPI).
- Concurrency: an in-process lock per (route, farmer, key) makes a retry that arrives while the first is running wait and replay (so vision/LLM run once); the unique index is the cross-process backstop (loser rolls back, its photos are deleted, it returns the stored row, never a 500).
- Not covered: `POST /v1/scans/{id}/photos` (an interactive step, appends photos) and `POST /v1/scans/{id}/crop` (already idempotent for the same crop).
- CORS `allow_headers` now includes `Idempotency-Key`. Login is checked before the key.
- Extra: `ExpertRequestIn.crop_id` (optional) so a question without a scan can name its crop; stored on the row and shown to staff.
- DEV DATABASE: `backend/farmtrack.db` (the smoke-test DB) predates the new columns and `create_all` never alters tables, so `init_db()` now also adds missing NULLABLE columns and indexes (`app/db/session.py add_missing_columns`, dev/test only; production runs Alembic). Checked on a copy of that file. Postgres not tested here (no server).

## 4. AlertOut.scan_id
- Optional `scan_id`, read from `AlertRow.payload["scan_id"]` (no new column; the `expert_advice` alert already stored it). The evaluator now sets it for the rain wash-off reminder (spray found by its time) and the waiting-period alert (by day and product) when that spray was logged from a scan's advice; the push `data` also carries `scan_id`. Weather risks (scab, leaf spot, blight) belong to the field and have none.

## 5. Admin expert requests
- API `GET /admin/api/v1/expert-requests?status=open|resolved|all&limit=` and `POST .../{id}/resolve {note}`; page `/admin/expert-requests` (nav entry, dashboard card) with CSRF, origin check and the admin CSP. Columns: farmer, crop (request, else scan, else farmer's main crop), text, scan link, created, status, note.
- New columns `resolved_at`, `resolution` (JSON {note, via}) on `expert_requests`. Resolving a review task also closes the open expert requests of that scan (via `review_task`). Statuses stay open/resolved (`ExpertRequestOut` unchanged).
- QUESTION: closing records a staff note only; the farmer is not messaged and the app has no route to read an answer. If the owner wants an in-app reply, it needs a design (alert or a GET route).

## 6. DEMO_DISEASE_HINTS
- `Crop=disease_id[:confidence];Crop=...` (documented in `app/vision/hints.py` and `.env.example`). Validated: crop name, disease id of the catalogue (real ids contain spaces, ( ) and commas, so those are allowed; never ; : =), confidence 0-1 (default 0.8). Malformed entries are skipped with a log warning; one entry per crop (last wins, warned). The spec's example repeated `Apple=`; I read it as "another entry", not as a rotation.
- Only steers the STUB (also when `disease_provider=model` falls back to it). `ENV=prod`: refused at start-up (`InsecureConfigurationError`) and ignored by the factory. The stub crop identifier honours the app's `client_crop` (tested through the real providers).

## 7. Packaging and ops (Docker UNTESTED: the daemon is not running)
- `fcm` extra is `cryptography>=42`, NOT firebase-admin: `FcmPushProvider` signs with PyJWT RS256 and calls the HTTP v1 API with httpx; it never imports firebase-admin.
- `docker-entrypoint.sh` runs `python -m alembic upgrade head` (10 attempts, 3 s apart, while Postgres starts) unless `AUTO_MIGRATE=0`, then `exec`s the CMD. The image sets `AUTO_MIGRATE=1` and installs the `pg` and `fcm` extras (`--build-arg EXTRAS="pg"` for a smaller image); the app's own `ensure_schema` (ENV=prod) then finds the schema current. Several replicas: `AUTO_MIGRATE=0` and migrate once per deploy. A database made earlier by `create_all` needs `alembic stamp head` first, otherwise `upgrade head` fails with "table exists". Healthcheck start-period raised to 90 s. Reviewed only; please build once.
- `.env.example` lists all 42 Settings fields plus the variables read from the environment (ALERT_*, AUTO_MIGRATE, SEED_DEMO, ZOHO_*, OPEN_METEO_API_KEY, POSTGRES_*), with one-line comments. `tests/test_ops_files.py` proves it (Settings fields, env reads found by scanning `app/`, compose variables) and that the example's SECRET_KEY/ADMIN_API_KEY placeholders are rejected by the prod guard (they are shorter than the minimum on purpose).
- There are NO SMS settings in the code (only `LogSmsSender`); the example says so instead of inventing any.
- `ZOHO_*` and `OPEN_METEO_API_KEY` are read from `os.environ`, not through Settings, so they work from compose's `env_file` but NOT from a `.env` read by a local `make run`. Suggest moving them into Settings later.
- `ruff check .` flagged S105/S106 in `scripts/dump_api_fixtures.py` (written by the mobile agent while I worked; fake placeholder tokens). I did not edit it; `pyproject.toml` has a narrow per-file ignore for those two rules.

## 8. contracts/openapi.json
- Regenerated with `python -m app.export_openapi ../contracts/openapi.json` and compared with the previous file programmatically: 0 removed, 0 changed fields; 3 route description texts extended (scans, spray-logs, expert-requests POST); 14 additions: `Idempotency-Key` header parameter on the three POST routes, 400 response on spray-logs and expert-requests, `AlertOut.scan_id`, `ExpertRequestIn.crop_id`, descriptions on 3 `SprayLogIn` fields, two admin paths, `ExpertRequestAdminOut`, `ExpertRequestResolveIn`.

## Status of the contract requests in docs/design-notes/platform.md
- 1 (scan-less requests invisible to staff): solved with the admin list instead of a nullable `ReviewTaskRow.scan_id`. 2 (`client_request_id`): done. 3 (`AlertOut` scan link): done as `scan_id`. 4 (`rules_auto_advice_diseases` setting existed already; the FCM extra is `cryptography`): done.
