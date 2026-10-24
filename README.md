# Private Flow

Android floating-bubble dictation with local Voxtype transcription on your own computer.

## What this version does

- Keeps your existing keyboard.
- Shows a draggable lavender bubble beside eligible focused text fields.
- Tap to record, then ✓ to finish; hold to record and release to finish; X cancels.
- Shows a live microphone waveform and an Android recording notification.
- Sends 16-kHz mono PCM WAV over your encrypted Tailscale connection.
- Runs the installed Voxtype with an explicitly local Whisper configuration.
- Inserts at the original selection, preserving surrounding text.
- If the field, selection, or existing content changes, copies the transcript instead of inserting into an unexpected destination.
- Hides in password, number, date/time, and phone-number fields.
- Uses single-use, 15-minute pairing codes and hashed per-device bearer credentials.
- No cloud fallback, analytics, transcript history, or audio persistence after the request completes.

This is an independent implementation, not a patched Wispr APK. The bubble's colors, shapes, and controls use Wispr's official Android demonstration as a visual reference. Complete screen-by-screen or pixel-perfect parity is **not verified**. Local rewriting/polishing, banking-app exclusions, streaming text, and all manufacturer-specific background recovery are not implemented.

## Build

Requires JDK 17 or 21, Android SDK platform/build tools 35, Gradle 8.13.

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

Only captured audio goes to the bridge; existing editor text stays on Android. The bridge processes audio in a private RAM-backed temporary directory on Linux and removes it after completion, timeout, or failure. Cancellation prevents insertion but an already-uploaded request may finish on the computer before its temporary files are removed. The receiving app controls text after insertion; clipboard fallback follows Android clipboard handling. Tailscale may relay encrypted packets; no external service receives plaintext audio through this implementation.

## Verification

`python -m unittest discover -s bridge -v` checks authentication, code reuse rejection, hashed credential storage, malformed WAV rejection, and busy handling. Set `PRIVATE_FLOW_TEST_WAV` to a spoken WAV fixture for real Voxtype integration; `PRIVATE_FLOW_EXPECTED_TEXT` sets its expected phrase.

`scripts/verify_emulator.py` additionally exercises actual Android pairing, overlay controls, foreground microphone capture, emulator microphone injection, Voxtype transcription, and field insertion. It currently targets the locally installed API-35 Pixel-7 emulator and uses its authenticated gRPC control endpoint. Its prerequisites and fixture are local test infrastructure, not APK runtime dependencies.

## UI reference

https://wisprflow.ai/android

https://docs.wisprflow.ai/articles/5906198129-starting-your-first-dictation-on-android

`references/contact-sheet.jpg` is extracted from Wispr's publicly hosted Android demonstration for local visual comparison, not bundled into the APK.
