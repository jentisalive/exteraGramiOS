# Device acceptance checks

These checks are pending until the full client compiles with the owner's API credentials and is installed on the target phone. A passing interpreter probe alone is not client acceptance.

1. Install the generated IPA using the intended jailbreak/sideload environment. Verify launch, the application-group container, login and session persistence after force quit.
2. Open Settings → Plugins, import the unchanged `inglish.plugin`, enable it and send `Привет, мир! 🌍` to Saved Messages. Verify that the actual delivered text is `Privet, mir! 🌍`.
3. Disable the plugin and verify Cyrillic is delivered unchanged. Test a media caption and ensure no invalid entity ranges or accidental loss of attachment/reply/thread metadata.
4. Toggle Translit through both its settings switch and chat-menu action. Relaunch the app and verify the saved state is restored.
5. Import an ordinary WAV/MP3/M4A sound and `sound_actions (3).plugin`. Select the sound for text, voice, round video, archive and delete actions. Verify each supported local event without changing the original plugin source.
6. With the client open, receive a private message and a group message. Verify separate configured sounds, bot exclusion, Telegram mute settings and per-chat exceptions. Background custom notification sound replacement is not supported by this preview.
7. Switch between two accounts and confirm each event uses the triggering account's peers. The original Sound Actions exception settings are shared; equal peer IDs in two accounts inherit that plugin's original limitation.
8. Disable Sound Actions and verify audio players, menus and hooks are released. Import a malformed plugin and verify a readable error while the client remains usable.
9. Verify unsupported Java/Android plugins fail explicitly rather than appearing compatible. Check native audio errors in Runtime logs.

Do not publish this as a complete exteraGram iOS release until the applicable checks pass and known limits are documented in the release notes.
