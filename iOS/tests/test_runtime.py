import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
EFFECTS = []
sys.modules["_extera_native"] = types.SimpleNamespace(send=lambda value: EFFECTS.append(json.loads(value)))

from extera_runtime import PluginManager, inspect_plugin


PROBE = '''
from base_plugin import BasePlugin, HookResult, HookStrategy, MethodHook, MenuItemData, MenuItemType
from hook_utils import find_class
from ui.settings import Switch, Header, Text
__id__ = "probe"
__name__ = "Runtime probe"
__version__ = "1.0"
class H(MethodHook):
    def __init__(self, p): self.p = p
    def after_hooked_method(self, args): self.p.set_setting("event_count", self.p.get_setting("event_count", 0) + 1)
class Plugin(BasePlugin):
    def on_plugin_load(self):
        self.add_on_send_message_hook()
        self.hook_all_methods(find_class("org.telegram.messenger.MessagesController"), "deleteMessages", H(self))
        self.add_menu_item(MenuItemData(menu_type=MenuItemType.CHAT_ACTION_MENU, text="Toggle", on_click=self.toggle))
    def toggle(self, context): self.set_setting("enabled", not self.get_setting("enabled", True))
    def create_settings(self):
        return [Header(text="Probe"), Switch(key="enabled", default=True), Text(text="Page", create_sub_fragment=lambda: [Text(text="Child")])]
    def on_send_message_hook(self, account, params):
        if not self.get_setting("enabled", True): return HookResult()
        params.message = params.message.replace("привет", "privet")
        return HookResult(strategy=HookStrategy.MODIFY, params=params)
'''


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manager = PluginManager(self.root / "Documents", self.root / "Support")
        self.probe = self.root / "probe.plugin"
        self.probe.write_text(PROBE, encoding="utf-8")
        EFFECTS.clear()

    def tearDown(self):
        for key in list(self.manager.instances):
            self.manager.enable(key, False)
        self.temporary.cleanup()

    def install_probe(self):
        self.manager.install(self.probe)
        self.manager.enable("probe", True)

    def test_import_does_not_execute_and_rejects_duplicate_id(self):
        self.manager.install(self.probe)
        self.assertEqual(self.manager.instances, {})
        self.assertFalse(self.manager.registry["probe"]["enabled"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.manager.install(self.probe)

    def test_text_hook_and_disable_cleanup(self):
        self.install_probe()
        original = {"message": "привет 🌍", "path": None}
        self.assertEqual(self.manager.send(7, original)["message"], "privet 🌍")
        self.assertEqual(original["message"], "привет 🌍")
        self.manager.enable("probe", False)
        self.assertFalse(self.manager.send_hooks)
        self.assertFalse(self.manager.method_hooks)
        self.assertFalse(self.manager.menus)
        self.assertEqual(self.manager.send(7, original)["message"], "привет 🌍")

    def test_settings_and_enabled_state_survive_restart(self):
        self.install_probe()
        self.manager.set_setting("probe", "enabled", False)
        restarted = PluginManager(self.root / "Documents", self.root / "Support")
        self.assertIn("probe", restarted.instances)
        self.assertFalse(restarted.get_setting("probe", "enabled", True))
        self.manager = restarted

    def test_native_event_and_menu_dispatch(self):
        self.install_probe()
        self.manager.request({"op": "event", "event": "delete_message", "account": 42})
        self.assertEqual(self.manager.get_setting("probe", "event_count"), 1)
        menu = self.manager.request({"op": "menus", "menu": "chat"})["items"][0]
        self.manager.request({"op": "menu_click", "item": menu["id"], "account": 42})
        self.assertFalse(self.manager.get_setting("probe", "enabled"))

    def test_nested_settings_callbacks(self):
        self.install_probe()
        rows = self.manager.settings_page("probe")["rows"]
        page = self.manager.request({"op": "callback", "id": "probe", "callback": rows[2]["callback"]})
        self.assertEqual(page["rows"][0]["text"], "Child")

    def test_rejects_path_traversal_metadata_and_syntax_errors(self):
        self.probe.write_text('__id__ = "../escape"', encoding="utf-8")
        with self.assertRaises(ValueError): self.manager.install(self.probe)
        self.probe.write_text('this is not python !', encoding="utf-8")
        with self.assertRaises(SyntaxError): self.manager.install(self.probe)
        self.assertFalse(self.manager.registry)

    def test_failed_load_cleans_partial_hooks(self):
        self.probe.write_text(PROBE.replace('self.add_on_send_message_hook()', 'self.add_on_send_message_hook(); raise RuntimeError("failure")'), encoding="utf-8")
        self.manager.install(self.probe)
        with self.assertRaisesRegex(RuntimeError, "failure"): self.manager.enable("probe", True)
        self.assertFalse(self.manager.send_hooks)
        self.assertFalse(self.manager.registry["probe"]["enabled"])

    def test_send_hook_failure_keeps_original_text(self):
        self.probe.write_text(PROBE.replace('params.message = params.message.replace("привет", "privet")', 'params.message = "bad"; raise RuntimeError("failure")'), encoding="utf-8")
        self.install_probe()
        result = self.manager.send(42, {"message": "привет"})
        self.assertEqual(result["message"], "привет")
        self.assertTrue(any("failure" in line for line in self.manager.log_lines))

    def test_interrupted_load_disables_suspect(self):
        self.install_probe()
        (self.root / "Support" / "loading.json").write_text('{"id": "probe"}')
        restarted = PluginManager(self.root / "Documents", self.root / "Support")
        self.assertNotIn("probe", restarted.instances)
        self.assertFalse(restarted.registry["probe"]["enabled"])

    def test_account_context_is_not_shared_between_notifications(self):
        from client_utils import get_messages_controller
        from hook_utils import find_class
        from base_plugin import MethodHook
        self.install_probe()
        owners = []
        class Hook(MethodHook):
            def after_hooked_method(self, param):
                owners.append(get_messages_controller().getUser(99).first_name)
        self.manager.add_method_hook("probe", find_class("org.telegram.messenger.NotificationsController"), "processNewMessages", Hook())
        for account, name in ((1, "Account A"), (2, "Account B"), (1, "Account A")):
            self.manager.request({"op": "event", "event": "notification", "account": account,
                                  "peers": [{"dialog_id": 99, "first_name": name, "bot": False}]})
        self.assertEqual(owners, ["Account A", "Account B", "Account A"])

    def test_arbitrary_java_methods_are_not_silently_accepted(self):
        from hook_utils import find_class
        from base_plugin import MethodHook
        self.assertIsNone(find_class("android.view.View"))
        with self.assertRaises(NotImplementedError):
            self.manager.add_method_hook("probe", find_class("org.telegram.messenger.MessagesController"), "anything", MethodHook())


@unittest.skipUnless(os.environ.get("EXTERA_SAMPLE_DIR"), "Original user-supplied samples are local-only")
class OriginalPluginTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    tearDown = RuntimeTests.tearDown
    def sample(self, name):
        self.manager.install(Path(os.environ["EXTERA_SAMPLE_DIR"]) / name)
        plugin_id = inspect_plugin(Path(os.environ["EXTERA_SAMPLE_DIR"]) / name)[0]["id"]
        self.manager.enable(plugin_id, True)
        return self.manager.instances[plugin_id]

    def test_original_translit_text_caption_switch_and_menu(self):
        plugin = self.sample("inglish.plugin")
        result = self.manager.request({"op": "send", "account": 1, "params": {"message": "Привет, мир! 🌍", "caption": "Щука"}})
        self.assertEqual(result["message"], "Privet, mir! 🌍")
        self.assertEqual(result["caption"], "Schuka")
        self.assertEqual(len(self.manager.settings_page("translit")["rows"]), 3)
        menu = self.manager.request({"op": "menus", "menu": "chat"})["items"][0]
        self.manager.request({"op": "menu_click", "item": menu["id"], "account": 1})
        self.assertEqual(self.manager.send(1, {"message": "Привет"})["message"], "Привет")
        self.assertEqual(EFFECTS[-1]["command"], "bulletin")

    def test_original_sound_actions_events_picker_and_cleanup(self):
        plugin = self.sample("sound_actions (3).plugin")
        path = self.manager.documents / "Audio" / "test.wav"
        path.write_bytes(b"fake-for-native-command-test")
        for action in ("text", "voice", "round", "archive", "delete", "delete_message", "notification_private", "notification_group"):
            plugin.set_setting("sound_" + action, str(path))
        plugin._preload_sound(str(path))
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.name.startswith("Thread-"):
                thread.join(timeout=2)
        self.assertTrue(any(x["command"] == "audio_prepare" for x in EFFECTS))
        self.assertIn(str(path), plugin._audio_candidates())
        self.assertGreater(len(self.manager.settings_page("sound_actions")["rows"]), 20)
        self.manager.request({"op": "send", "account": 1, "params": {"message": "test", "path": None}})
        for event in ("archive", "delete", "delete_message"):
            self.manager.request({"op": "event", "account": 1, "event": event})
        before = sum(x["command"] == "audio_play" for x in EFFECTS)
        self.manager.request({"op": "event", "account": 1, "event": "notification", "peers": [{"dialog_id": 99, "bot": True}]})
        self.assertEqual(sum(x["command"] == "audio_play" for x in EFFECTS), before)
        self.manager.request({"op": "event", "account": 1, "event": "notification", "peers": [{"dialog_id": 99, "bot": False}]})
        self.assertEqual(sum(x["command"] == "audio_play" for x in EFFECTS), before + 1)
        self.manager.enable("sound_actions", False)
        self.assertTrue(any(x["command"] == "audio_release" for x in EFFECTS))
        self.assertFalse(self.manager.method_hooks)


if __name__ == "__main__":
    unittest.main()
