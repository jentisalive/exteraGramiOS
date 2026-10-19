"""No UIKit calls are made from Python: native effects are queued by the host."""
import json
import threading

_local = threading.local()
_manager = None


def command(name, **payload):
    import _extera_native
    _extera_native.send(json.dumps({"command": name, **payload}, ensure_ascii=False))


def manager():
    if _manager is None:
        raise RuntimeError("Plugin manager has not been initialized")
    return _manager


def account():
    return getattr(_local, "account", 0)
