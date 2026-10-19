"""Persistent plugin lifecycle and JSON boundary shared by iOS and host tests."""
import ast
import copy
import hashlib
import json
import os
import re
import sys
import threading
import traceback
import types
import uuid
from pathlib import Path

import ios_bridge
from base_plugin import BasePlugin, HookResult, HookStrategy, AppEvent

MAX_PLUGIN_BYTES = 2 * 1024 * 1024
SUPPORTED_METHODS = {
    ("org.telegram.messenger.MessagesController", "addDialogToFolder"): "archive",
    ("org.telegram.messenger.MessagesController", "deleteDialog"): "delete",
    ("org.telegram.messenger.MessagesController", "deleteDialogs"): "delete_bulk",
    ("org.telegram.messenger.MessagesController", "deleteMessages"): "delete_message",
    ("org.telegram.messenger.NotificationsController", "processNewMessages"): "notification",
}


def atomic_json(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(data, encoding="utf-8")
    os.replace(temporary, path)


def inspect_plugin(path):
    path = Path(path)
    if path.stat().st_size > MAX_PLUGIN_BYTES:
        raise ValueError("Plugin exceeds the 2 MiB limit")
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    metadata = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "__id__", "__name__", "__version__", "__description__", "__author__"
                ):
                    try:
                        metadata[target.id.strip("_")] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
    plugin_id = metadata.get("id")
    if not isinstance(plugin_id, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,95}", plugin_id):
        raise ValueError("Plugin must declare a literal, valid __id__")
    for key, value in metadata.items():
        if not isinstance(value, str):
            raise ValueError(f"Plugin metadata {key} must be a string")
    metadata.setdefault("name", plugin_id)
    metadata.setdefault("version", "unknown")
    metadata["sha256"] = hashlib.sha256(source.encode()).hexdigest()
    return metadata, source


class _JavaList:
    def __init__(self, values):
        self.values = values

    def size(self):
        return len(self.values)

    def get(self, index):
        return self.values[index]


class _Unhook:
    def __init__(self, manager, key):
        self.manager, self.key = manager, key

    def unhook(self):
        self.manager.method_hooks.pop(self.key, None)


class PluginManager:
    def __init__(self, documents, support):
        self.documents, self.support = Path(documents), Path(support)
        self.plugins_dir = self.documents / "Plugins"
        for directory in (self.plugins_dir, self.support, self.documents / "Audio", self.documents / "Files"):
            directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.instances, self.modules, self.errors = {}, {}, {}
        self.send_hooks, self.method_hooks, self.menus, self.callbacks = {}, {}, {}, {}
        self.peers = {}
        self.log_lines = []
        self.settings = self._read_json("settings.json", {})
        self.registry = self._read_json("plugins.json", {})
        ios_bridge._manager = self
        # If the process died while executing a plugin's load handler, don't
        # automatically execute that same plugin again on the next launch.
        crash = self._read_json("loading.json", {})
        suspect = crash.get("id")
        if suspect in self.registry:
            self.registry[suspect]["enabled"] = False
            self.errors[suspect] = "Disabled after an interrupted load; inspect the plugin before retrying."
            self._save_registry()
        atomic_json(self.support / "loading.json", {})
        for plugin_id, info in list(self.registry.items()):
            if info.get("enabled"):
                try:
                    self.enable(plugin_id, True)
                except Exception as error:
                    self.errors[plugin_id] = str(error)

    def _read_json(self, name, default):
        path = self.support / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
        except FileNotFoundError:
            return copy.deepcopy(default)
        except (ValueError, OSError):
            self.log("runtime", f"Invalid {name}; retained a recovery copy")
            if path.exists():
                path.replace(path.with_suffix(".invalid-" + uuid.uuid4().hex + ".json"))
            return copy.deepcopy(default)

    def _save_registry(self):
        atomic_json(self.support / "plugins.json", self.registry)

    def log(self, plugin_id, text):
        with self.lock:
            self.log_lines.append(f"[{plugin_id}] {text}")
            del self.log_lines[:-300]

    def get_setting(self, plugin_id, key, default=None):
        with self.lock:
            return copy.deepcopy(self.settings.get(plugin_id, {}).get(key, default))

    def set_setting(self, plugin_id, key, value):
        json.dumps(value)  # Refuse values that cannot be persisted.
        with self.lock:
            self.settings.setdefault(plugin_id, {})[key] = copy.deepcopy(value)
            atomic_json(self.support / "settings.json", self.settings)

    def install(self, path, replace=False):
        metadata, source = inspect_plugin(path)
        plugin_id = metadata["id"]
        if plugin_id in self.registry and not replace:
            raise ValueError("A plugin with this ID already exists. Remove it before importing a replacement.")
        self.enable(plugin_id, False)
        destination = self.plugins_dir / (plugin_id + ".plugin")
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(source, encoding="utf-8")
        os.replace(temporary, destination)
        self.registry[plugin_id] = {**metadata, "enabled": False}
        self._save_registry()
        return metadata

    def _clear(self, plugin_id):
        self.send_hooks.pop(plugin_id, None)
        for collection in (self.method_hooks, self.menus, self.callbacks):
            for key, value in list(collection.items()):
                if value[0] == plugin_id:
                    collection.pop(key, None)
        self.instances.pop(plugin_id, None)
        module = self.modules.pop(plugin_id, None)
        if module:
            sys.modules.pop(module.__name__, None)

    def enable(self, plugin_id, enabled):
        if not enabled:
            plugin = self.instances.get(plugin_id)
            if plugin:
                try:
                    plugin.on_plugin_unload()
                except Exception:
                    self.log(plugin_id, traceback.format_exc())
            self._clear(plugin_id)
            if plugin_id in self.registry:
                self.registry[plugin_id]["enabled"] = False
                self._save_registry()
            return
        if plugin_id in self.instances:
            return
        if plugin_id not in self.registry:
            raise ValueError("Unknown plugin")
        atomic_json(self.support / "loading.json", {"id": plugin_id})
        try:
            metadata, source = inspect_plugin(self.plugins_dir / (plugin_id + ".plugin"))
            if metadata["id"] != plugin_id:
                raise ValueError("Plugin ID changed on disk")
            module = types.ModuleType("extera_user_" + uuid.uuid4().hex)
            module.__file__ = str(self.plugins_dir / (plugin_id + ".plugin"))
            sys.modules[module.__name__] = module
            self.modules[plugin_id] = module
            exec(compile(source, module.__file__, "exec"), module.__dict__)
            classes = [value for value in module.__dict__.values()
                       if isinstance(value, type) and value is not BasePlugin
                       and issubclass(value, BasePlugin) and value.__module__ == module.__name__]
            if len(classes) != 1:
                raise ValueError("Plugin must define exactly one BasePlugin subclass")
            plugin = classes[0]()
            plugin._bind(self, plugin_id)
            self.instances[plugin_id] = plugin
            plugin.on_plugin_load()
            self.registry[plugin_id].update(metadata, enabled=True)
            self.errors.pop(plugin_id, None)
            self._save_registry()
        except Exception as error:
            plugin = self.instances.get(plugin_id)
            if plugin:
                try:
                    plugin.on_plugin_unload()
                except Exception:
                    pass
            self._clear(plugin_id)
            self.registry[plugin_id]["enabled"] = False
            self.errors[plugin_id] = str(error)
            self.log(plugin_id, traceback.format_exc())
            self._save_registry()
            raise
        finally:
            atomic_json(self.support / "loading.json", {})

    def remove(self, plugin_id):
        if plugin_id not in self.registry:
            raise ValueError("Unknown plugin")
        self.enable(plugin_id, False)
        (self.plugins_dir / (plugin_id + ".plugin")).unlink(missing_ok=True)
        self.registry.pop(plugin_id)
        self.errors.pop(plugin_id, None)
        self._save_registry()

    def add_menu(self, plugin_id, item):
        if item.menu_type.value not in ("main", "chat"):
            raise NotImplementedError("Only main and chat menus are currently supported")
        key = plugin_id + ":" + (item.item_id or uuid.uuid4().hex)
        self.menus[key] = (plugin_id, item)
        return key

    def remove_menu(self, plugin_id, item_id):
        if item_id in self.menus and self.menus[item_id][0] == plugin_id:
            self.menus.pop(item_id)

    def add_method_hook(self, plugin_id, cls, method_name, hook):
        event = SUPPORTED_METHODS.get((getattr(cls, "name", None), method_name))
        if event is None:
            raise NotImplementedError(f"No iOS event adapter for {cls}.{method_name}")
        key = uuid.uuid4().hex
        self.method_hooks[key] = (plugin_id, event, hook)
        return [_Unhook(self, key)]

    def _callback(self, plugin_id, callback):
        key = uuid.uuid4().hex
        self.callbacks[key] = (plugin_id, callback)
        return key

    def rows(self, plugin_id, rows):
        result = []
        for row in rows:
            value = {"kind": row.kind, "text": row.text, "subtext": row.subtext or ""}
            if row.kind == "switch":
                value.update(key=row.key, value=bool(self.get_setting(plugin_id, row.key, row.default)))
            callback = getattr(row, "create_sub_fragment", None)
            if callback:
                value["callback"] = self._callback(plugin_id, lambda cb=callback: cb())
            elif getattr(row, "on_click", None):
                value["callback"] = self._callback(plugin_id, lambda cb=row.on_click: cb(None))
            if getattr(row, "on_change", None):
                value["on_change"] = self._callback(plugin_id, row.on_change)
            result.append(value)
        return result

    def settings_page(self, plugin_id):
        plugin = self.instances.get(plugin_id)
        if plugin is None:
            raise ValueError("Enable this plugin before opening its settings")
        # A new root page supersedes callbacks from the previous presentation.
        self.callbacks = {k: v for k, v in self.callbacks.items() if v[0] != plugin_id}
        return {"rows": self.rows(plugin_id, plugin.create_settings())}

    def send(self, account, params):
        current = copy.deepcopy(params)
        for plugin_id, _ in sorted(list(self.send_hooks.items()), key=lambda item: -item[1]):
            plugin = self.instances.get(plugin_id)
            if plugin is None:
                continue
            candidate = types.SimpleNamespace(**copy.deepcopy(current))
            try:
                result = plugin.on_send_message_hook(account, candidate)
                if not isinstance(result, HookResult):
                    raise TypeError("Send hook must return HookResult")
                if result.strategy == HookStrategy.CANCEL:
                    return {"cancelled": True, **current}
                if result.strategy == HookStrategy.MODIFY:
                    value = vars(result.params if result.params is not None else candidate)
                    # The native adapter supports text/caption replacement, not
                    # arbitrary object mutation or media replacement.
                    for key in ("message", "caption"):
                        if key in value:
                            if value[key] is not None and not isinstance(value[key], str):
                                raise TypeError(f"{key} must be text or None")
                    current.update({k: value[k] for k in ("message", "caption") if k in value})
            except Exception:
                self.log(plugin_id, traceback.format_exc())
        return {"cancelled": False, **current}

    def event(self, event, data):
        args = []
        if event == "notification":
            messages = []
            for peer in data.get("peers", []):
                peer_id = int(peer["dialog_id"])
                self.peers[(ios_bridge.account(), peer_id)] = peer
                messages.append(types.SimpleNamespace(dialog_id=peer_id))
            args = [_JavaList(messages)]
        param = types.SimpleNamespace(args=args, thisObject=None, result=None)
        for plugin_id, name, hook in list(self.method_hooks.values()):
            if name == event:
                try:
                    hook.before_hooked_method(param)
                    hook.after_hooked_method(param)
                except Exception:
                    self.log(plugin_id, traceback.format_exc())

    def request(self, data):
        old_account = ios_bridge.account()
        ios_bridge._local.account = int(data.get("account", 0))
        try:
            operation = data["op"]
            plugin_id = data.get("id")
            if operation == "list":
                return {"plugins": [{**info, "error": self.errors.get(key, "")}
                                    for key, info in self.registry.items()]}
            if operation == "import":
                return self.install(data["path"])
            if operation == "enable":
                self.enable(plugin_id, bool(data["enabled"]))
                return {}
            if operation == "remove":
                self.remove(plugin_id)
                return {}
            if operation == "settings":
                return self.settings_page(plugin_id)
            if operation == "callback":
                owner, callback = self.callbacks[data["callback"]]
                if owner != plugin_id or owner not in self.instances:
                    raise ValueError("Expired callback")
                if "key" in data:
                    self.set_setting(plugin_id, data["key"], data["value"])
                    rows = callback(data["value"])
                else:
                    rows = callback()
                return {"rows": self.rows(owner, rows)} if isinstance(rows, list) else {}
            if operation == "setting":
                if plugin_id not in self.instances:
                    raise ValueError("Plugin is disabled")
                self.set_setting(plugin_id, data["key"], data["value"])
                return {}
            if operation == "menus":
                return {"items": [{"id": key, "text": item.text, "subtext": item.subtext or ""}
                                  for key, (owner, item) in sorted(list(self.menus.items()), key=lambda x: -x[1][1].priority)
                                  if item.menu_type.value == data.get("menu", "main")]}
            if operation == "menu_click":
                _, item = self.menus[data["item"]]
                item.on_click(data.get("context", {}))
                return {}
            if operation == "send":
                return self.send(ios_bridge.account(), data["params"])
            if operation == "event":
                self.event(data["event"], data)
                return {}
            if operation == "lifecycle":
                for key, plugin in list(self.instances.items()):
                    try:
                        plugin.on_app_event(AppEvent(data["event"]))
                    except Exception:
                        self.log(key, traceback.format_exc())
                return {}
            if operation == "logs":
                return {"lines": list(self.log_lines)}
            raise ValueError("Unknown runtime operation")
        finally:
            ios_bridge._local.account = old_account


_runtime = None


def initialize(documents, support):
    global _runtime
    _runtime = PluginManager(documents, support)


def dispatch(request_json):
    try:
        if _runtime is None:
            raise RuntimeError("Python runtime is not initialized")
        return json.dumps(_runtime.request(json.loads(request_json)), ensure_ascii=False)
    except Exception as error:
        if _runtime:
            _runtime.log("runtime", traceback.format_exc())
        return json.dumps({"error": str(error)}, ensure_ascii=False)
