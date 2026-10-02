"""Key injection back ends."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol, TextIO

from autotyper.events import BACKSPACE, ENTER, TAB


class Injector(Protocol):
    def press(self, key: str, hold_s: float) -> None: ...


class RecordingInjector:
    """Test double: records what would have been pressed."""

    def __init__(self) -> None:
        self.pressed: list[tuple[str, float]] = []

    def press(self, key: str, hold_s: float) -> None:
        self.pressed.append((key, hold_s))


class PynputInjector:
    """Real OS-level key injection via pynput.

    keyboard/special/sleep are injectable for tests; by default they come
    from pynput and time.sleep.
    """

    def __init__(
        self,
        keyboard: Any | None = None,
        special: Mapping[str, Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if keyboard is None or special is None:
            from pynput.keyboard import Controller, Key

            keyboard = keyboard or Controller()
            special = special or {BACKSPACE: Key.backspace, ENTER: Key.enter, TAB: Key.tab}
        self._kb = keyboard
        self._special = dict(special)
        self._sleep = sleep

    def press(self, key: str, hold_s: float) -> None:
        k = self._special.get(key, key)
        self._kb.press(k)
        self._sleep(hold_s)
        self._kb.release(k)


class TerminalInjector:
    """Dry-run back end: renders keys to a text stream in real time."""

    def __init__(self, out: TextIO | None = None) -> None:
        self._out = out
        self.buffer = ""

    def _write(self, s: str) -> None:
        out = self._out if self._out is not None else sys.stdout
        out.write(s)
        out.flush()

    def press(self, key: str, hold_s: float) -> None:
        if key == BACKSPACE:
            if self.buffer and self.buffer[-1] not in "\n\t":
                self._write("\b \b")
            self.buffer = self.buffer[:-1]
        elif key == ENTER:
            self._write("\n")
            self.buffer += "\n"
        elif key == TAB:
            self._write("\t")
            self.buffer += "\t"
        else:
            self._write(key)
            self.buffer += key
