class _Row:
    kind = "text"

    def __init__(self, text="", subtext=None, icon=None, **kwargs):
        self.text, self.subtext, self.icon = text, subtext, icon
        self.__dict__.update(kwargs)


class Header(_Row):
    kind = "header"


class Divider(_Row):
    kind = "divider"


class Text(_Row):
    kind = "text"


class Switch(_Row):
    kind = "switch"

    def __init__(self, key, text="", default=False, **kwargs):
        super().__init__(text=text, key=key, default=default, **kwargs)
