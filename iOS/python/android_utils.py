from ios_bridge import command, manager


def log(message):
    manager().log("runtime", str(message))


def run_on_ui_thread(callback, delay=0):
    # Native bridge effects dispatch to the main queue. Python stays under the GIL.
    if delay:
        raise NotImplementedError("Delayed UI callbacks are not supported by this SDK")
    return callback()


def copy_to_clipboard(text):
    command("clipboard", text=str(text))


class Fragment:
    def finishFragment(self):
        command("pop_settings")
