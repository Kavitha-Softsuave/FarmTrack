# backendauth: username + password login (19 Oct 2026)

Done: `POST /v1/auth/login` (TokenOut, 401 `invalid_credentials`, 429 `rate_limited` + Retry-After), PBKDF2-HMAC-SHA256 hashes
(`app/security/passwords.py`, 210k iterations), `farmers.username` / `password_hash` in migration 0001, OTP routes off unless
`OTP_LOGIN_ENABLED`, demo logins `f001`..`f050` / `DEMO_PASSWORD`, admin "Set login" + "Create farmer" (pages and API).

Doubts and decisions:
- Phone is REQUIRED in "Create farmer" (the brief said optional): `farmers.phone` is NOT NULL and unique, and making it nullable
  would touch the schema and every phone consumer. Phone is still only a contact field, not the login. The owner dropped the
  expert phone call, so the expert-requests page does NOT show phone numbers (task 4c removed; a test checks that it stays hidden).
- Limits: 20 attempts per 10 min per IP (all attempts) and 8 WRONG passwords per 10 min per username (only failures count, so good
  logins never lock a farmer out; the right password is refused too once the window is full). The limiters are in-memory like the
  others: with several workers the limits multiply. Many farmers behind one carrier NAT could share the IP limit of 20.
- Setting a login (reset) revokes that farmer's open refresh tokens (access tokens live out their 60 minutes). The audit log keeps
  the username, never the password. Passwords have a 6..128 character rule only; the 128 cap is an input guard, not a policy.
- Dev convenience: at start-up in dev/test (or SEED_DEMO=1) demo farmers that exist but have no password (a database made before
  this change) get their demo login; farmers with a password, another username, or outside data/farmers.csv are untouched. Prod
  without SEED_DEMO never gets a demo password. `DEMO_PASSWORD` defaults to the public `farm1234`: do not run SEED_DEMO=1 on a
  server real farmers can reach (there is no start-up guard for it).
- Tests lower the PBKDF2 cost (`passwords.DEFAULT_ITERATIONS = 1000` in tests/conftest.py) and set `OTP_LOGIN_ENABLED=true` so the
  OTP tests keep running; the stored hash carries its iteration count. Created farmers get ids F051, F052 ... (next free F-number),
  with no station/lat/lon (weather by station needs those added later).
