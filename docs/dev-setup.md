# Developer setup: what is not in the repository

The repository runs and tests fully offline with the defaults: no account, key or download is needed for that. This page lists what a
new developer has to bring or create for everything else, and why it is not committed.

## 1. To run and test (always needed)
| Need | Version | How |
|---|---|---|
| Python | 3.11 or newer (developed on 3.13) | `cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"` (Unix: `.venv/bin/python`) |
| Flutter | 3.47.7 stable (Dart 3.13.5) | install the same version; then `cd mobile && flutter pub get` |

`backend/farmtrack.db` (development database with 50 demo farmers, logins `f001`..`f050` / `farm1234`) and `backend/storage/` are created by the
app on first start. `.env` is optional: without it the offline defaults apply (copy `.env.example` to `.env` to change anything).

## 2. Real crop and disease models (optional; without them vision is a stub that finds no disease)
- Install the extras: `pip install -e ".[ml]"` (CPU PyTorch is enough, no GPU), then set `CROP_ID_PROVIDER=model` and `DISEASE_PROVIDER=model`.
- Weights, about 300 MB, are downloaded from Hugging Face on first use into `backend/storage/models` at pinned revisions
  (`backend/app/vision/inference.py`): `ixrbhii/leaf-crop-detector-16-convnext`, `ixrbhii/leaf-crop-detector-36-convnext`,
  `ixrbhii/apple-disease-convnext`, `neghani/plantvillage-mobilenetv2`. On a machine without internet copy that folder from another machine.
- The first scan after a start takes 10 to 30 s while the models load (the backend warms them up in the background).
- The evaluation kits in `data/model_test/` need their own torch environment (`data/model_test/requirements.txt`).

## 3. Leaf photos (not committed: unknown licence)
`data/images/**` holds web-sourced test photos and photos collected from users. Ask the project owner for the folder and copy it to the same
place (the label files and `data/images/README.md` are in the repository). Needed by: `backend/scripts/evaluate_vision.py`,
`backend/scripts/dump_api_fixtures.py`, `mobile/test_live/`, `data/scripts/prepare_testset.py`. The backend vision tests skip themselves without them.

## 4. Building an Android APK (steps that worked on 24 Oct 2026, Windows 11, all tools under `D:\tools`)
Versions: Flutter 3.47.7 (Dart 3.13.5), Temurin JDK 17.0.20, Android command-line tools 11076708, platform-tools, platforms 35 and 36,
build-tools 36.0.0, CMake 3.22.1; NDK r28c and Gradle download themselves on the first build (first build about 16 min, later ones 2 to 3 min).
1. Flutter: unzip `flutter_windows_3.47.7-stable.zip` (storage.googleapis.com/flutter_infra_release/releases/stable/windows/, 1.9 GB) to `D:\tools\flutter`.
2. JDK: unzip Temurin 17 (`api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse`) and rename the folder to `D:\tools\jdk17`.
3. Android SDK: unzip the command-line tools to `D:\tools\android-sdk\cmdline-tools\latest`, then with `JAVA_HOME` set:
   `sdkmanager --sdk_root=D:\tools\android-sdk --licenses` (answer y) and
   `sdkmanager --sdk_root=D:\tools\android-sdk platform-tools "platforms;android-36" "platforms;android-35" "build-tools;36.0.0" "cmake;3.22.1"`.
4. `flutter config --android-sdk D:\tools\android-sdk --jdk-dir D:\tools\jdk17`, then `cd mobile && flutter pub get`.
5. `powershell -ExecutionPolicy Bypass -File mobile\tool\build_apk.ps1 [-ServerUrl http://<PC>:8000] [-Debug] [-AllAbis]`. Tool folders: parameters
   (`-JdkDir -AndroidSdkDir -FlutterDir -ToolsDir`) or the variables `FARMTRACK_TOOLS` (default `D:\tools`), `FARMTRACK_JDK`, `FARMTRACK_ANDROID_SDK`,
   `FARMTRACK_FLUTTER`. The release APK is signed with the debug key (no release keystore) and goes to `dist/` (not committed); arm64 only unless `-AllAbis`.

Pitfalls found: (a) `mobile/android/gradle.properties` has `kotlin.incremental=false`, because with the project on D: and the pub cache on C: the Kotlin
plugin fails with "this and base files have different roots"; (b) the root `.gitignore` once ignored every folder called `storage/`, which silently
dropped `mobile/lib/core/storage/token_store.dart` from the repository (now `/storage/`; the file was re-created from its tests and callers, review it).

Emulator (optional, worked): `sdkmanager emulator "system-images;android-35;google_apis;x86_64"`, `avdmanager create avd -n ft35 -k <that image> -d pixel_5`,
`emulator -avd ft35 -no-window -no-audio -gpu swiftshader_indirect` (Windows Hypervisor Platform was usable: `emulator -accel-check`), build a debug APK for it with
`flutter build apk --debug --target-platform android-x64 --dart-define=API_BASE_URL=http://10.0.2.2:8000`, then `adb install -r` and `adb exec-out screencap -p`.
iOS has not been looked at.

## 5. Testing the app on a phone against your own machine
Phone and PC on one network that lets devices talk to each other (a phone hotspot works; many office Wi-Fi networks do not). Start the backend
with `scripts/start_backend_for_phone.ps1`, then in the app: login screen or Settings, "Server", `http://<PC address>:8000`. On Windows the firewall
must allow port 8000 for that network type (an administrator may be needed). The script prefers a separate copy of Python at `C:\siva\tools\python313`
because that machine's firewall blocked the installed one; without the copy it falls back to the venv Python.

## 6. Keys and accounts (only for the real services, none for development)
| Setting (`.env`) | For | Status |
|---|---|---|
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_PROVIDER=openai` | LLM wording of advice, ask, embeddings | not committed; model `gpt-4o-mini` shuts down 14 Jan 2027 |
| `GOOGLE_TTS_API_KEY`, `TTS_PROVIDER=google` | server speech, `scripts/generate_prompt_audio.py` | no audio files exist yet; the phone's own voice is used; steps in `docs/voice-package.md` |
| `ZOHO_*`, `ZOHO_PROVIDER=real` | spray history from the client's CRM | untested skeleton; field names are assumptions |
| Firebase project, `google-services.json`, `FCM_CREDENTIALS_FILE` | push notifications | not set up (steps in `docs/design-notes/mobile2a.md`) |
| `SECRET_KEY`, `ADMIN_API_KEY`, `POSTGRES_PASSWORD` | production | the app refuses to start in production with the defaults |
| `OPEN_METEO_API_KEY` | commercial weather | free endpoint is non-commercial |
| SMS gateway | OTP (switched off) | not built |

## 7. Not code
Native Hindi review of every text, agronomist answers, the client's approved lists for more crops, real field photos: see `docs/open-questions.md`.
