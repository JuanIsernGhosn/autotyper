"""Timed keystroke events produced by the planner and consumed by the runner."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

BACKSPACE = "backspace"
ENTER = "enter"
TAB = "tab"
WORD_BACKSPACE = "word_backspace"  # Option+Backspace on macOS
SPECIAL_KEYS = frozenset({BACKSPACE, ENTER, TAB, WORD_BACKSPACE})


@dataclass(frozen=True)
class Event:
    """One key press.

    key: a single character, or one of SPECIAL_KEYS.
    delay_ms: time to wait before pressing this key.
    hold_ms: how long the key stays held down.
    note: free text for the dry-run view ("error:neighbor", "fix", ...).
    """

    key: str
    delay_ms: float
    hold_ms: float
    note: str = ""


def replay(events: Iterable[Event]) -> str:
    """Apply the events to an empty text buffer and return the result."""
    buf: list[str] = []
    for e in events:
        if e.key == BACKSPACE:
            if buf:
                buf.pop()
        elif e.key == WORD_BACKSPACE:
            while buf and not buf[-1].isspace():
                buf.pop()
        elif e.key == ENTER:
            buf.append("\n")
        elif e.key == TAB:
            buf.append("\t")
        else:
            buf.append(e.key)
    return "".join(buf)
