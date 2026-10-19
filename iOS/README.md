# exteraGram for iOS — Python plugin port

Native Telegram for iOS with an embedded CPython interpreter and an initial compatibility layer for exteraGram `.plugin` files. The existing Android source tree is retained unchanged.

**Status: implementation preview, not a verified Telegram client release.** The Python layer has host tests, and CI builds a separate iOS Simulator probe. A complete client IPA needs the owner's Telegram API credentials and a successful full client build. Simulator checks do not prove installation or operation on an iPhone running iOS 18.6.2.

## Build with GitHub Actions

1. Obtain an application `api_id` and `api_hash` at [my.telegram.org/apps](https://my.telegram.org/apps).
2. Open this repository's **Settings → Secrets and variables → Actions → New repository secret**. Add `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`. Do not commit either value to source control.
3. Before merging the PR, open the latest **Actions → exteraGram iOS** push run and choose **Re-run all jobs** after it completes. Once the workflow is on `main`, **Run workflow** is also available; select the branch you want to build.
4. The workflow runs Python tests, the native iOS Simulator probe, and native client compilation. The simulator probe and client build run in parallel. With API credentials it also packages and uploads the `exteraGram-iOS` artifact containing `exteraGram-iOS.ipa`; without them, compilation uses placeholders and produces no client download. A download is a test build; check the complete workflow result before using it.

The IPA is ad-hoc signed for testing in an appropriate jailbreak/sideload installation environment. This workflow does not create an Apple development certificate, provisioning profile, App Store build, or APNs identity. Installation with the user's particular jailbreak and TrollStore Lite setup remains a device test.

All Apple compilation runs on GitHub Actions. The standalone runtime probe uses `macos-15` / Xcode 16.4 with an iOS 18 simulator; the full Telegram client requires `macos-26` / Xcode 26.6. Without API credentials, CI still attempts a compile-only integration check using placeholder values; it does not package or publish that as a usable client IPA. The client targets upstream's iOS deployment target (15.0), including iOS 18.6.2. Dependencies are pinned in [`upstream.json`](upstream.json); the Python support archive is SHA-256 checked before extraction.

## Use plugins

- Open **Settings → Plugins → Import plugin or audio…** and select a `.plugin` file in Files.
- Imported plugins start disabled. Turn the switch on to run one; tap its row to open its settings. Swipe left to remove it.
- Main-menu plugin actions appear under **Plugin actions** in the manager. Chat-menu actions appear when tapping the chat's More button; **Chat options…** retains access to the upstream menu.
- Import audio through the same picker, then select it in the plugin's settings. Files are copied into `Documents/Audio`; iOS codec support applies.
- Inspect **Runtime logs** if loading, a hook, or native audio playback fails.

Plugins execute inside the client's process with access to its data. They are not a security sandbox. The loader validates metadata and syntax before installation, handles ordinary Python exceptions, cleans up registrations on disable, and disables a plugin after an interrupted load. It cannot safely terminate an infinite Python loop or recover from arbitrary native corruption.

## Compatibility

| Area | Implemented | Limits |
| --- | --- | --- |
| Python | Embedded CPython 3.13, standard library | No Java VM, Chaquopy, general Android SDK, or arbitrary binary pip wheels |
| Lifecycle | Import, enable/disable, persistent settings, load/unload | App stop is not guaranteed by iOS; plugins must release resources on unload |
| Send hooks | Text and media captions before enqueue, priority order, DEFAULT/MODIFY/CANCEL | CANCEL cancels the entire enqueue batch. Forwarded messages are unchanged. Media path is a classification hint, not an exported file path |
| Formatting | Stale text entities removed after text changes | Modified text/captions lose formatting and custom-emoji entities |
| UI | Header, Divider, Text, Switch, nested settings, bulletins, clipboard | This is a supported subset of the SDK, not a claim of full SDK-version compatibility |
| Menus | Main and chat actions | Message/profile context menus and some specialized chat types are not yet connected |
| Sound Actions | MediaPlayer adapter to AVAudioPlayer; send, archive, delete and foreground incoming-message adapters | No arbitrary Java method interception. iOS audio formats/session rules apply. Background/APNs plugin sound replacement is not implemented |
| Multi-account | Explicit account propagated to events, per-account peer cache | The original plugin's own saved settings/exception list remains shared across accounts |

The original supplied **Translit 1.3.1** (`inglish.plugin`) and **Sound Actions 1.5.0** were exercised unchanged against the Python compatibility layer. Those private test inputs are not redistributed here. Their actual operation inside the complete Telegram app is a separate integration/device check.

The Java-named method adapters are deliberately limited to after-event callbacks for `MessagesController.addDialogToFolder`, `deleteDialog`, `deleteMessages`, and `NotificationsController.processNewMessages`. Only the connected native event paths are supported. Bulk-delete hooks and before-method interception are not supported. Unrecognized classes return no adapter; unrecognized methods raise an error. This is not a general Xposed replacement.

## Source and validation

- [`python/`](python): compatibility SDK and persistent loader.
- [`native/`](native): Objective-C CPython bridge, plugin manager/settings UI, AVAudioPlayer adapter, TelegramCore hooks.
- [`scripts/apply_overlay.py`](scripts/apply_overlay.py): checks the exact upstream commit and each source anchor before applying the integration.
- [`tests/`](tests): lifecycle/error/account-isolation tests and a real interpreter/audio simulator probe.
- [Official Telegram iOS source](https://github.com/TelegramMessenger/Telegram-iOS), [Python iOS embedding documentation](https://docs.python.org/3.13/using/ios.html), [Python Apple Support](https://github.com/beeware/Python-Apple-support).

The first client build excludes Telegram app extensions; background notifications, widgets, Siri, iCloud, and share extensions are not release-ready. Preserve upstream license notices and publish the corresponding client source when distributing builds. This overlay remains covered by the repository's license; CPython and its bundled dependencies retain their own licenses.
