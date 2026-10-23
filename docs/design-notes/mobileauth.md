# MOBILE-AUTH notes: user name + password login in the app (19 Oct 2026)

Done: no OTP and no phone number in the app. `/login` is one screen (user name, password with a big eye button, green tick), the
app always asks for it; `POST /v1/auth/login` with the per-install device id; the last user name is prefilled from SharedPreferences
(`last_username`), the password is never stored. OTP screen, `/login/otp` route, numeric keypad, `OtpRequest*`/`OtpVerifyIn` models,
`requestOtp`/`verifyOtp` and the `PREFILL_DEV_OTP` config are removed. Tests rewritten (login success, wrong password, empty fields,
connection error, 429, eye, prefill, device id, 64 dp targets, 320x568 at text 2.0 in both languages, keyboard open), contract
fixtures `auth_login` / `auth_login_invalid` read by the real model (I re-ran `dump_api_fixtures.py` once after the voice prompts changed, so the voice catalogue fixtures match), live check logs in with `f001` / `farm1234` (31 calls pass).

Doubts for the owner or the team:
- **Typing a password is the hardest step for a farmer who cannot read well** (the old keypad was easy; now a full keyboard). Mitigations
  in place: last user name prefilled, the eye shows what was typed, "wrong" is spoken. Consider a short numeric PIN, or a card with the
  user name and password printed for the field team. No "forgot password" exists: only the admin can set a login (see `backendauth.md`),
  and the app has no prompt that tells the farmer whom to call. Hindi login words (`यूज़र नेम`, `पासवर्ड`, `लॉग इन`) are transliterated
  English: native review needed (the whole login prompt set is a draft like the others).
- **Rate limit speech:** 429 `rate_limited` speaks the generic `error_try_again`, not "wait a few minutes". The server allows 20 tries per
  10 minutes per IP (many farmers behind one carrier NAT may share it) and 8 wrong passwords per user name; a dedicated prompt (`login_wait`)
  would help once the owner sees the real numbers.
- **Client-side check:** a user name outside 3 to 40 of `a-z 0-9 . _ -` or a password under 6 characters is answered with `login_wrong` without
  calling the server (the server's `LoginIn` has no minimum length, so it would answer a plain 401 anyway). If the rules change, change
  `_usernameShape` and `_minPassword` in `lib/features/auth/login_screen.dart`. The password is sent as typed (not trimmed).
- **OTP leftovers:** the OTP prompts (`ask_phone`, `ask_otp`, `otp_sent`, `otp_wrong`, `phone_invalid`, `otp_resend`) stay in `voice/prompts.json`
  because `validate_prompts.py` requires them; the OTP server routes stay behind `OTP_LOGIN_ENABLED` and their fixtures are skipped by the
  contract test. `login_ok` and `login_again` got new texts ("You are in. Welcome." / "Please log in again to come in.").
- **Keyboard on small phones:** while the keyboard is up, `VoiceScaffold` hides the caption and the "voice missing" banner so the fields keep
  room (also helps the Ask-type screen). The username field is focused on first open (the password when a user name is prefilled), the
  password field uses the plain "visible password" keyboard and no autofill hints (so Google does not offer to save the password).
  None of this was tried on a real phone or keyboard (no Android SDK here). The mock accepts `f000` to `f099`; the real backend only `f001` to `f050`.
