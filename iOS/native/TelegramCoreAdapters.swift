import Foundation
import Postbox
import ExteraPlugins

// Android-style dialog IDs are used only at the compatibility boundary. Native
// operations continue to use the complete Postbox peer namespace and ID.
func exteraDialogId(_ peerId: PeerId) -> Int64 {
    let value = peerId.id._internalGetInt64Value()
    return peerId.namespace == Namespaces.Peer.CloudUser ? value : -value
}

func exteraPrepareMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> [EnqueueMessage]? {
    var result: [EnqueueMessage] = []
    for message in messages {
        switch message {
        case let .message(text, attributes, inlineStickers, mediaReference, threadId, replyToMessageId, replyToStoryId, localGroupingKey, correlationId, bubbleUpEmojiOrStickersets):
            let path: Any
            if let file = mediaReference?.media as? TelegramMediaFile {
                path = file.isVoice ? "voice.ogg" : (file.isInstantVideo ? "round.mp4" : (file.fileName ?? "attachment"))
            } else {
                path = mediaReference == nil ? NSNull() : "attachment"
            }
            let response = EPPluginHost.shared().request([
                "op": "send", "account": account.peerId.id._internalGetInt64Value(),
                "params": ["message": text, "caption": mediaReference == nil ? NSNull() : text,
                           "path": path, "dialog_id": exteraDialogId(peerId)]
            ])
            if response["cancelled"] as? Bool == true {
                // Preserve the caller's result cardinality by cancelling the
                // complete enqueue batch, rather than silently dropping slots.
                return nil
            }
            let modifiedMessage = response["message"] as? String ?? text
            let modifiedCaption = response["caption"] as? String ?? text
            let updated = mediaReference != nil && modifiedCaption != text ? modifiedCaption : modifiedMessage
            // Text entity ranges are UTF-16 offsets. A plugin may change the
            // number of code units; stale ranges must never be sent to Telegram.
            let updatedAttributes = updated == text ? attributes : attributes.filter { !($0 is TextEntitiesMessageAttribute) }
            result.append(.message(text: updated, attributes: updatedAttributes,
                                   inlineStickers: updated == text ? inlineStickers : [:],
                                   mediaReference: mediaReference, threadId: threadId,
                                   replyToMessageId: replyToMessageId, replyToStoryId: replyToStoryId,
                                   localGroupingKey: localGroupingKey, correlationId: correlationId,
                                   bubbleUpEmojiOrStickersets: bubbleUpEmojiOrStickersets))
        case .forward:
            result.append(message)
        }
    }
    return result
}

func exteraNotifyIncoming(accountPeerId: PeerId, groups: [([Message], PeerGroupId, Bool, MessageHistoryThreadData?)]) {
    var peers: [[String: Any]] = []
    var seen = Set<PeerId>()
    for (messages, _, notify, _) in groups where notify {
        for message in messages {
            let peerId = message.id.peerId
            guard seen.insert(peerId).inserted, let peer = message.peers[peerId] else { continue }
            var data: [String: Any] = ["dialog_id": exteraDialogId(peerId), "bot": false]
            if let user = peer as? TelegramUser {
                data["first_name"] = user.firstName ?? ""
                data["last_name"] = user.lastName ?? ""
                data["bot"] = user.botInfo != nil
            } else if let channel = peer as? TelegramChannel {
                data["title"] = channel.title
            } else if let group = peer as? TelegramGroup {
                data["title"] = group.title
            }
            peers.append(data)
        }
    }
    if !peers.isEmpty {
        EPPluginHost.shared().emitForeground([
            "op": "event", "event": "notification", "account": accountPeerId.id._internalGetInt64Value(), "peers": peers
        ])
    }
}
