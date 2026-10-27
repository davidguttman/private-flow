# Releases

Private Flow currently distributes Android APKs for direct sideloading. There is no configured Play Store, package-registry, container, or hosted-site release pipeline.

## Version policy

Use SemVer: patch for fixes only, minor for backward-compatible user-visible capabilities or installation improvements, major for breaking behavior or configuration changes. Update `versionName` in `app/build.gradle.kts` and increment Android `versionCode` for every distributed update.

## Sideload release

1. Merge the reviewed change into `main` and clean up its task worktree.
2. Update version metadata, then run `./gradlew :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug` using JDK 17 or 21 and Android SDK 35.
3. Run applicable emulator regressions from `README.md`, including an update installation over the previous APK. Verify the APK package, version, and signing certificate match the intended upgrade.
4. Commit the version, push `main`, and tag the release `v<version>`.
5. Deliver the verified APK as `private-flow-<version>.apk` with its SHA-256 checksum. Keep signing material private and out of git.

The existing sideload channel uses the debug build signed with the existing local Android debug signing identity. This is not a Play Store or production-release signing setup. Preserve that signing identity for in-place updates; switching keys requires a separately planned migration. Do not uninstall the existing app merely to work around an incompatible signature, because uninstalling removes local pairing and preferences.
