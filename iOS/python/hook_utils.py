"""Explicit event adapters, not a Java VM or arbitrary method-hook emulator."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeEventClass:
    name: str


_CLASSES = {
    "org.telegram.messenger.MessagesController",
    "org.telegram.messenger.NotificationsController",
}


def find_class(name):
    return NativeEventClass(name) if name in _CLASSES else None
