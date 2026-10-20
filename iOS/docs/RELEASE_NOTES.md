Experimental native iOS preview of exteraGram, based on the pinned official Telegram-iOS source with embedded CPython 3.13.

- Import and enable supported `.plugin` files without rebuilding the client for each plugin.
- Includes plugin settings, text/caption hooks, menu actions and selected native event/audio adapters.
- Python tests, the iOS Simulator runtime probe and the full arm64 client build passed for this source commit. The packaged application passed ad-hoc signature verification.

Compatibility is partial. Arbitrary Android/Java/Xposed APIs and background notification sound replacement are not supported. Telegram app extensions and APNs provisioning are excluded from this preview.

The IPA is ad-hoc signed for testing in the intended jailbreak/sideload environment. Installation, login and plugin operation on an actual iOS 18.6.2 device with TrollStore Lite have not yet been verified. This is a test build, not a stable release.

Download `exteraGram-iOS.ipa`; `SHA256SUMS.txt` contains its checksum. The GitHub source archives correspond to the port repository; `iOS/upstream.json` pins Telegram-iOS and Python dependencies. See `iOS/README.md` and `iOS/docs/DEVICE_CHECKS.md` for usage, compatibility and remaining device checks.
