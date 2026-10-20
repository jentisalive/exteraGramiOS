from types import SimpleNamespace
from ios_bridge import manager, account as current_account


class _MessagesController:
    def __init__(self, account):
        self.account = account

    def getUser(self, peer_id):
        peer = manager().peers.get((self.account, int(peer_id)))
        return SimpleNamespace(**peer) if peer else None

    def getChat(self, peer_id):
        peer = manager().peers.get((self.account, -int(peer_id)))
        return SimpleNamespace(**peer) if peer else None


def get_messages_controller(account=None):
    return _MessagesController(current_account() if account is None else account)
