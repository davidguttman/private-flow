# Private Flow

Android floating-bubble dictation with local Voxtype transcription on your own computer.

## What this version does

- Keeps your existing keyboard.
- Shows a draggable lavender bubble beside eligible focused text fields. Remembers the side and relative vertical position after a completed drag, including across service/process restarts; clamps to the current display. First use defaults to the right side, halfway down the screen.
- Shrinks to an animated small dot after 5 seconds idle; tap or hold starts dictation directly. Shrinking pauses while interacting, recording, or transcribing. The dot keeps a stable touch target of at least 48 dp; opacity changes only the artwork, never the input window.
- Saves bubble size (70%, 85%, 100%, 115%), opacity (20–100%), and idle-shrink preference immediately, with a live preview.
- Tap to record, then ✓ to finish; hold to record and release to finish; X cancels.
- Shows a live microphone waveform and an Android recording notification.
- Replaces Done with a spinner and “Transcribing” immediately after submission; only Cancel remains active until the result arrives.
- Sends 16-kHz mono PCM WAV over your encrypted Tailscale connection.
- Uses the host’s existing Voxtype configuration by default: model, language, local engine, spoken punctuation, word replacements, and configured post-processing command. No separate phone profile is created.
- Removes pause ellipses (`...` / `…`) locally after transcription, without rewriting words or changing ordinary sentence punctuation and paragraph breaks.
- Inserts through Android’s accessibility editing connection at the original selection, preserving actual surrounding text. Placeholder strings exposed as accessibility text are never copied into the editor. Your existing keyboard remains selected; native paste is the fallback when an editing connection is unavailable.
- If the field, selection, or existing content changes, copies the transcript instead of inserting into an unexpected destination.
- Hides in password, number, date/time, and phone-number fields.
- Uses single-use, 15-minute pairing codes and hashed per-device bearer credentials.
- No cloud fallback, analytics, transcript history, or audio persistence after the request completes.

This is an independent implementation, not a patched Wispr APK. The bubble's colors, shapes, and controls use Wispr's official Android demonstration as a visual reference. Complete screen-by-screen or pixel-perfect parity is **not verified**. Local rewriting/polishing, banking-app exclusions, streaming text, and all manufacturer-specific background recovery are not implemented.

## Build

Requires JDK 17 or 21 and Android SDK platform/build tools 35. The Gradle wrapper supplies Gradle 8.13. Set `ANDROID_HOME` to your SDK directory or add `sdk.dir=/path/to/Android/sdk` in an untracked `local.properties`.

```
./gradlew :app:assembleDebug :app:lintDebug
```

The sideloadable APK is at `app/build/outputs/apk/debug/app-debug.apk`.

## Run the bridge

Requires Python 3.11+ and an installed, configured `voxtype` that already works locally, including its configured model. No Python dependencies.

```
python bridge/server.py --bind YOUR_TAILSCALE_IP --port 8767
```

By default the bridge reads `$XDG_CONFIG_HOME/voxtype/config.toml` (normally `~/.config/voxtype/config.toml`) on every request. Changes to that normal configuration apply to the next phone dictation. `--config /path/to/config.toml` is only an explicit override. The old bridge-only config is now a test fixture, not an application default.

Because Voxtype 0.6.0’s file command skips its daemon text stage, the bridge applies the configured spoken punctuation, explicit replacement dictionary, and `output.post_process` command before the requested pause-ellipsis cleanup. Desktop typing, clipboard delivery, hotkeys, and pre/post-output hooks are not run on the computer; text is returned to the phone. Configured post-processing commands run as configured, so keep those commands local for private processing. Remote transcription backends are rejected rather than silently sending phone audio elsewhere.

The bridge only accepts loopback or Tailscale CGNAT bind addresses. Do not expose this HTTP endpoint via public forwarding: transport encryption is provided by Tailscale. The Android app rejects ordinary unencrypted public/LAN endpoints and does not follow redirects. HTTP is allowed only for literal Tailscale CGNAT IPv4 addresses (`100.64.0.0/10`) and the local verification endpoints `127.0.0.1`, `localhost`, and `10.0.2.2`; DNS names require HTTPS.

The terminal displays a single-use pairing code valid for 15 minutes. In the app:

1. Grant microphone, overlay, and accessibility permissions.
2. Enter the computer's Tailscale endpoint and pairing code.
3. Tap **Pair with computer**, then **Check connection**.
4. Open a text field in your usual app and tap the floating bubble.

Phone and computer must be on an appropriately authorized Tailscale network. Android may require **Allow restricted settings** from the app-info menu before enabling accessibility for a sideloaded APK.

To invalidate all paired devices, remove the credential database at `~/.local/share/private-flow/devices.json` while the bridge is not running, then relaunch it. Restarting the bridge generates a new pairing code but preserves existing device credentials.

## Privacy boundary

Only captured audio goes to the bridge; existing editor text stays on Android. The bridge processes audio in a private RAM-backed temporary directory on Linux and removes it after completion, timeout, or failure. Cancellation prevents insertion but an already-uploaded request may finish on the computer before its temporary files are removed. The receiving app controls text after insertion; native paste / clipboard fallback follows Android clipboard handling. Tailscale may relay encrypted packets; no external service receives plaintext audio through this implementation.

## Verification

Run the endpoint-validation and bubble-position preference JVM tests (no emulator required) and portable-script prerequisite tests with:

```
./gradlew :app:testDebugUnitTest
uv run python -m unittest discover -s scripts -v
```

The Android UI scripts discover `adb` from `ANDROID_HOME`, then `ANDROID_SDK_ROOT`, then `PATH`. Set `ANDROID_SERIAL` to select the test emulator (default `emulator-5556`). They expect an already-running API-35 Pixel-7-sized emulator, installed debug APK, microphone/notification/overlay/accessibility permissions, and the normal keyboard enabled. Touch and insertion scripts expect the app's saved connection to point to `http://127.0.0.1:8768` with a test token; their local transcript fixtures do not authenticate. Use a disposable test emulator, not a personal device: these scripts change accessibility settings, install APKs, edit fields, and save ignored local evidence.

For placeholder regression, set `PRIVATE_FLOW_BASELINE_APK` to an existing **0.2.1 debug APK** signed with the same key as the current debug APK. The script fails before starting its fixture if this prerequisite is missing. Build the current app and editor fixture with `./gradlew :app:assembleDebug :app:assembleDebugAndroidTest`, and install the fixture APK from `app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk` before running. The baseline is an explicitly supplied local artifact, not downloaded or bundled. The touch/appearance scripts additionally require Pillow (for example, `uv run --with pillow python scripts/verify_touch_regression.py`).

`./gradlew :app:assembleDebugAndroidTest` builds a separate editor-fixture APK, never bundled into the shipped app. `scripts/verify_placeholder_insertion.py` first reproduces the old unmarked-Message-placeholder append using 0.2.1, then verifies empty fields, unmarked hints with/without hint metadata, actual typed Message, middle insertion, and selected-text replacement against the current APK. It uses real Android editing/microphone capture with a loopback transcript fixture and checks that the normal keyboard remains unchanged.

`python -m unittest discover -s bridge -v` checks authentication, code reuse rejection, hashed credential storage, malformed WAV rejection, inherited config / live config changes / text processing, private temporary-config cleanup, remote-backend rejection, and pause formatting. Set `PRIVATE_FLOW_TEST_WAV` to a spoken WAV fixture for real Voxtype integration; `PRIVATE_FLOW_EXPECTED_TEXT` sets its expected phrase.

`uv run python scripts/verify_bubble_position.py` checks first-run placement, real drags to both sides, saved preference wiring, accessibility-service rebinds, app process restarts, idle touch-window stability, and off-screen position clamping. It requires the debug app and editor-fixture APKs above, refuses non-emulator devices, and restores the original position keys and accessibility service settings on exit without replacing unrelated preferences. It does not record audio or need a bridge. Run the existing touch regression separately for recording/tap/shrink coverage.

`scripts/verify_touch_regression.py` (also available through `scripts/verify_appearance.py`) exercises actual bubble/dot taps across opacity and size settings, stable minimum hit targets, and Done-to-progress behavior against a deliberately delayed local HTTP fixture. It checks that repeated Done-area presses submit only once and that the returned text is inserted. This fixture tests Android interactions, not Voxtype inference.

`scripts/verify_emulator.py` additionally exercises actual Android pairing, overlay controls, foreground microphone capture, emulator microphone injection, Voxtype transcription, and field insertion. It requires `PRIVATE_FLOW_TEST_WAV`, working local Voxtype, `grpcio` and `protobuf`, and Python bindings generated from the installed Android emulator's gRPC protos (`emulator_controller_pb2.py`, `emulator_controller_pb2_grpc.py`, and their imports). Put the bindings on `PYTHONPATH` or set `PRIVATE_FLOW_EMULATOR_PROTO_DIR` to their directory. Set `PRIVATE_FLOW_EMULATOR_GRPC` if the local authenticated gRPC endpoint differs from `localhost:8556`. Set `PRIVATE_FLOW_EMULATOR_INI` to that emulator's running `pid*.ini` token file; otherwise the script requires exactly one such file under `$XDG_RUNTIME_DIR/avd/running` (Linux fallback: `/run/user/<current uid>/avd/running`). These settings must all identify the same emulator. The token is read locally, never committed. These prerequisites and the spoken fixture are local test infrastructure, not APK runtime dependencies.

## UI reference

https://wisprflow.ai/android

https://docs.wisprflow.ai/articles/5906198129-starting-your-first-dictation-on-android

`references/contact-sheet.jpg` is extracted from Wispr's publicly hosted Android demonstration for local visual comparison, not bundled into the APK.
