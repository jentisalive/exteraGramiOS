"""The supported exteraGram API subset, implemented by the iOS host."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class HookStrategy(Enum):
    DEFAULT = 0
    CANCEL = 1
    MODIFY = 2


@dataclass
class HookResult:
    strategy: HookStrategy = HookStrategy.DEFAULT
    params: Any = None
    request: Any = None
    response: Any = None


class MenuItemType(Enum):
    MAIN_MENU = "main"
    CHAT_ACTION_MENU = "chat"
    MESSAGE_CONTEXT_MENU = "message"
    PROFILE_ACTION_MENU = "profile"


class AppEvent(Enum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass
class MenuItemData:
    menu_type: MenuItemType
    text: str
    on_click: Callable
    icon: Optional[str] = None
    subtext: Optional[str] = None
    priority: int = 0
    item_id: Optional[str] = None


class MethodHook:
    def before_hooked_method(self, param):
        pass

    def after_hooked_method(self, param):
        pass


class BasePlugin:
    def __init__(self):
        self._manager = None
        self._plugin_id = None

    def _bind(self, manager, plugin_id):
        self._manager, self._plugin_id = manager, plugin_id

    def log(self, message):
        self._manager.log(self._plugin_id, str(message))

    def get_setting(self, key, default=None):
        return self._manager.get_setting(self._plugin_id, key, default)

    def set_setting(self, key, value, reload_settings=False):
        self._manager.set_setting(self._plugin_id, key, value)

    def export_settings(self):
        return dict(self._manager.settings.get(self._plugin_id, {}))

    def import_settings(self, settings, reload_settings=True):
        for key, value in settings.items():
            self.set_setting(key, value)

    def add_on_send_message_hook(self, priority=0):
        self._manager.send_hooks[self._plugin_id] = priority

    def add_menu_item(self, item):
        return self._manager.add_menu(self._plugin_id, item)

    def remove_menu_item(self, item_id):
        self._manager.remove_menu(self._plugin_id, item_id)

    def hook_all_methods(self, cls, method_name, hook):
        return self._manager.add_method_hook(self._plugin_id, cls, method_name, hook)

    def get_last_fragment(self):
        from android_utils import Fragment
        return Fragment()

    def on_plugin_load(self):
        pass

    def on_plugin_unload(self):
        pass

    def on_app_event(self, event_type):
        pass

    def create_settings(self):
        return []
