#!/usr/bin/env python3
"""Apply a small, checked overlay to exactly one pinned Telegram source revision."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

IOS = Path(__file__).resolve().parents[1]
LOCK = json.loads((IOS / "upstream.json").read_text())


def replace(root, path, old, new):
    file = root / path
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one patch anchor, got {count}")
    file.write_text(text.replace(old, new, 1))


def add_import(root, path):
    replace(root, path, "import Foundation\n", "import Foundation\nimport ExteraPlugins\n")


def add_dependency(root, path, name):
    file = root / path
    text = file.read_text()
    start = text.index('    name = "' + name + '",')
    end = text.index("\n)\n", start)
    section = text[start:end]
    if section.count("    deps = [\n") != 1:
        raise RuntimeError("Dependency anchor changed: " + name)
    section = section.replace("    deps = [\n", '    deps = [\n        "//submodules/ExteraPlugins",\n')
    file.write_text(text[:start] + section + text[end:])


def apply(root):
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != LOCK["commit"]:
        raise RuntimeError(f"Unsupported Telegram revision {head}; expected {LOCK['commit']}")
    target = root / "submodules/ExteraPlugins"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("EPPluginHost.h", "EPPluginHost.m", "EPPluginManagerController.h", "EPPluginManagerController.m", "BUILD"):
        shutil.copyfile(IOS / "native" / name, target / name)
    shutil.copyfile(IOS / "native/TelegramCoreAdapters.swift", root / "submodules/TelegramCore/Sources/ExteraPluginAdapters.swift")

    for path, name in (("submodules/TelegramCore/BUILD", "TelegramCore"), ("submodules/TelegramUI/BUILD", "TelegramUI"),
                       ("submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/BUILD", "PeerInfoScreen")):
        add_dependency(root, path, name)

    enqueue = "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    anchor = "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n"
    replace(root, enqueue, anchor, anchor + "    guard let messages = exteraPrepareMessages(account: account, peerId: peerId, messages: messages) else {\n        return .single(Array(repeating: nil, count: messages.count))\n    }\n")

    state = "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    replace(root, state, "                        strongSelf.notificationMessagesPipe.putNext(messages)",
            "                        exteraNotifyIncoming(accountPeerId: strongSelf.accountPeerId, groups: messages)\n                        strongSelf.notificationMessagesPipe.putNext(messages)")

    delete = "submodules/TelegramCore/Sources/TelegramEngine/Messages/DeleteMessagesInteractively.swift"
    add_import(root, delete)
    replace(root, delete, "        deleteMessagesInteractively(transaction: transaction, stateManager: account.stateManager, postbox: account.postbox, messageIds: messageIds, type: type, removeIfPossiblyDelivered: true)",
            '        deleteMessagesInteractively(transaction: transaction, stateManager: account.stateManager, postbox: account.postbox, messageIds: messageIds, type: type, removeIfPossiblyDelivered: true)\n        if !messageIds.isEmpty {\n            EPPluginHost.shared().emit(["op": "event", "event": "delete_message", "account": account.peerId.id._internalGetInt64Value()])\n        }')

    remove = "submodules/TelegramCore/Sources/TelegramEngine/Peers/RemovePeerChat.swift"
    add_import(root, remove)
    anchor = "        _internal_removePeerChat(account: account, transaction: transaction, mediaBox: account.postbox.mediaBox, peerId: peerId, reportChatSpam: reportChatSpam, deleteGloballyIfPossible: deleteGloballyIfPossible)"
    replace(root, remove, anchor, anchor + '\n        EPPluginHost.shared().emit(["op": "event", "event": "delete", "account": account.peerId.id._internalGetInt64Value()])')

    peers = "submodules/TelegramCore/Sources/TelegramEngine/Peers/TelegramEnginePeers.swift"
    add_import(root, peers)
    anchor = "                    _internal_updatePeerGroupIdInteractively(transaction: transaction, peerId: peerId, groupId: groupId._asGroup())\n                }"
    replace(root, peers, anchor, anchor + '\n                if groupId._asGroup() == .archive && !peerIds.isEmpty {\n                    EPPluginHost.shared().emit(["op": "event", "event": "archive", "account": self.account.peerId.id._internalGetInt64Value()])\n                }')

    settings = "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift"
    add_import(root, settings)
    replace(root, settings, "    if displaySetStatus {", '''    items[.advanced]!.append(PeerInfoScreenActionItem(id: 9001, text: "Plugins", icon: UIImage(systemName: "puzzlepiece.extension"), action: {
        EPPluginHost.shared().presentManager(account: context.account.peerId.id._internalGetInt64Value())
    }))

    if displaySetStatus {''')

    chat = "submodules/TelegramUI/Sources/ChatController.swift"
    add_import(root, chat)
    replace(root, chat, "    @objc func moreButtonPressed() {\n", '''    @objc func moreButtonPressed() {
        if case let .peer(peerId) = self.chatLocation {
            let account = self.context.account.peerId.id._internalGetInt64Value()
            let response = EPPluginHost.shared().request(["op": "menus", "menu": "chat", "account": account])
            if let items = response["items"] as? [[String: Any]], !items.isEmpty {
                let sheet = UIAlertController(title: "Plugins", message: nil, preferredStyle: .actionSheet)
                let nativeId = peerId.id._internalGetInt64Value()
                let dialogId = peerId.namespace == Namespaces.Peer.CloudUser ? nativeId : -nativeId
                for item in items {
                    guard let title = item["text"] as? String, let itemId = item["id"] as? String else { continue }
                    sheet.addAction(UIAlertAction(title: title, style: .default, handler: { _ in
                        EPPluginHost.shared().emit(["op": "menu_click", "item": itemId, "account": account, "context": ["dialog_id": dialogId]])
                    }))
                }
                sheet.addAction(UIAlertAction(title: "Chat options…", style: .default, handler: { [weak self] _ in
                    guard let self else { return }
                    self.moreBarButton.play()
                    self.moreBarButton.contextAction?(self.moreBarButton.containerNode, nil)
                }))
                sheet.addAction(UIAlertAction(title: "Cancel", style: .cancel))
                sheet.popoverPresentationController?.sourceView = self.moreBarButton.view
                sheet.popoverPresentationController?.sourceRect = self.moreBarButton.view.bounds
                self.present(sheet, animated: true)
                return
            }
        }
''')

    # The first sideload build intentionally excludes app extensions. This keeps
    # one Python interpreter in the main app and doesn't claim APNs provisioning.
    build = "build-system/Make/Make.py"
    replace(root, build, "self.disable_provisioning_profiles = False", "self.disable_provisioning_profiles = True")
    replace(root, build, "        self.common_args = [", '''        self.common_args = [
            '--//Telegram:disableExtensions',
            '--features=disable_legacy_signing',
            '--jobs=3',''')

    # rules_apple still embeds a provisioning profile unconditionally for a
    # device application, even when legacy signing is disabled. Omit that
    # embedding step only for the explicitly unsigned build; retain normal
    # profile validation for every other build configuration.
    rules = root / "build-system/bazel-rules/rules_apple/apple/internal/ios_rules.bzl"
    text = rules.read_text()
    start = text.index("def _ios_application_impl(ctx):")
    end = text.index("\ndef ", start + 1)
    section = text[start:end]
    anchor = "    if platform_prerequisites.platform.is_device:\n        processor_partials.append(\n            partials.provisioning_profile_partial("
    if section.count(anchor) != 1:
        raise RuntimeError("Unsigned application provisioning anchor changed")
    updated = section.replace(anchor, '    if (platform_prerequisites.platform.is_device and\n        (provisioning_profile or "disable_legacy_signing" not in features)):\n        processor_partials.append(\n            partials.provisioning_profile_partial(')
    rules.write_text(text[:start] + updated + text[end:])

    telegram = "Telegram/BUILD"
    text = (root / telegram).read_text()
    # Both frameworks link the in-app plugin host; they must not enforce the
    # app-extension API restriction on UIApplication/UI document picker APIs.
    for name in ("TelegramCoreFramework", "TelegramUIFramework"):
        start = text.index('    name = "' + name + '",')
        end = text.index("\n)\n", start)
        section = text[start:end]
        if section.count("extension_safe = True") != 1:
            raise RuntimeError("Framework extension-safe anchor changed: " + name)
        text = text[:start] + section.replace("extension_safe = True", "extension_safe = False") + text[end:]
    (root / telegram).write_text(text)
    # Change only the host application's name; retain upstream identifiers for
    # build targets. Folder access uses the normal Files interface.
    replace(root, telegram, "    <string>Telegram</string>\n    <key>CFBundleIdentifier</key>\n    <string>{telegram_bundle_id}</string>",
            "    <string>exteraGram</string>\n    <key>LSSupportsOpeningDocumentsInPlace</key>\n    <true/>\n    <key>CFBundleIdentifier</key>\n    <string>{telegram_bundle_id}</string>")
    replace(root, telegram, "    <key>UIFileSharingEnabled</key>\n    <false/>", "    <key>UIFileSharingEnabled</key>\n    <true/>")
    print("Applied iOS plugin overlay to", head)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("telegram", type=Path)
    apply(parser.parse_args().telegram.resolve())
