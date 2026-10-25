# Private Flow

Android floating-bubble dictation with local Voxtype transcription on your own computer.

## What this version does

- Keeps your existing keyboard.
- Shows a draggable lavender bubble beside eligible focused text fields.
- Shrinks to an animated small dot after 5 seconds idle; tap or hold starts dictation directly. Shrinking pauses while interacting, recording, or transcribing. The dot keeps a stable touch target of at least 48 dp; opacity changes only the artwork, never the input window.
- Saves bubble size (70%, 85%, 100%, 115%), opacity (20–100%), and idle-shrink preference immediately, with a live preview.
- Tap to record, then ✓ to finish; hold to record and release to finish; X cancels.
- Shows a live microphone waveform and an Android recording notification.
- Replaces Done with a spinner and “Transcribing” immediately after submission; only Cancel remains active until the result arrives.
- Sends 16-kHz mono PCM WAV over your encrypted Tailscale connection.
- Runs the installed Voxtype with an explicitly local Whisper configuration.
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

Requires Python 3.11+ and an installed `voxtype` with the `large-v3-turbo` model downloaded. No Python dependencies.

```
python bridge/server.py --bind YOUR_TAILSCALE_IP --port 8767
```

The bridge only accepts loopback or Tailscale CGNAT bind addresses. Do not expose this HTTP endpoint via public forwarding: transport encryption is provided by Tailscale. The Android app rejects ordinary unencrypted public/LAN endpoints and does not follow redirects.

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

`./gradlew :app:assembleDebugAndroidTest` builds a separate editor-fixture APK, never bundled into the shipped app. `scripts/verify_placeholder_insertion.py` first reproduces the old unmarked-Message-placeholder append using 0.2.1, then verifies empty fields, unmarked hints with/without hint metadata, actual typed Message, middle insertion, and selected-text replacement against the current APK. It uses real Android editing/microphone capture with a loopback transcript fixture and checks that the normal keyboard remains unchanged.

`python -m unittest discover -s bridge -v` checks authentication, code reuse rejection, hashed credential storage, malformed WAV rejection, and busy handling. Set `PRIVATE_FLOW_TEST_WAV` to a spoken WAV fixture for real Voxtype integration; `PRIVATE_FLOW_EXPECTED_TEXT` sets its expected phrase.

`scripts/verify_touch_regression.py` (also available through `scripts/verify_appearance.py`) exercises actual bubble/dot taps across opacity and size settings, stable minimum hit targets, and Done-to-progress behavior against a deliberately delayed local HTTP fixture. It checks that repeated Done-area presses submit only once and that the returned text is inserted. This fixture tests Android interactions, not Voxtype inference.

`scripts/verify_emulator.py` additionally exercises actual Android pairing, overlay controls, foreground microphone capture, emulator microphone injection, Voxtype transcription, and field insertion. It currently targets the locally installed API-35 Pixel-7 emulator and uses its authenticated gRPC control endpoint. Its prerequisites and fixture are local test infrastructure, not APK runtime dependencies.

## UI reference

https://wisprflow.ai/android

https://docs.wisprflow.ai/articles/5906198129-starting-your-first-dictation-on-android

`references/contact-sheet.jpg` is extracted from Wispr's publicly hosted Android demonstration for local visual comparison, not bundled into the APK.
