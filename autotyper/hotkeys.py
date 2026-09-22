"""Global pause/abort hotkeys via a pynput listener."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from autotyper.runner import Controls


def key_name(key: Any) -> str:
    name = getattr(key, "name", None)
    if isinstance(name, str):
        return name.lower()
    char = getattr(key, "char", None)
    if isinstance(char, str):
        return char.lower()
    return ""


class HotkeyListener:
    def __init__(
        self,
        controls: Controls,
        pause_key: str = "f8",
        abort_key: str = "esc",
        log: Callable[[str], None] = print,
    ) -> None:
        self.controls = controls
        self.pause_key = pause_key.lower()
        self.abort_key = abort_key.lower()
        self.log = log
        self._listener: Any | None = None

    def on_press(self, key: Any) -> None:
        name = key_name(key)
        if name == self.pause_key:
            self.controls.paused = not self.controls.paused
            self.log("pause requested" if self.controls.paused else "resume requested")
        elif name == self.abort_key:
            self.controls.aborted = True
            self.log("abort requested")

    def start(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self.on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
