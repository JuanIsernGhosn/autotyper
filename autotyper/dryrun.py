"""Human-readable views of an event list, for --dry-run."""

from __future__ import annotations

from collections.abc import Sequence

from autotyper.events import BACKSPACE, ENTER, TAB, Event, replay

_GLYPHS = {BACKSPACE: "⌫", ENTER: "⏎\n", TAB: "⇥"}


def transcript(events: Sequence[Event]) -> str:
    return "".join(_GLYPHS.get(e.key, e.key) for e in events)


def summary(events: Sequence[Event]) -> str:
    total_s = sum(e.delay_ms for e in events) / 1000
    final = replay(events)
    errors = sum(1 for e in events if e.note.startswith("error:"))
    cps = len(final) / total_s if total_s > 0 else 0.0
    return "\n".join(
        [
            f"duration: {total_s:.1f} s",
            f"chars: {len(final)}",
            f"keystrokes: {len(events)}",
            f"errors: {errors}",
            f"effective cps: {cps:.1f}",
        ]
    )


def verbose_lines(events: Sequence[Event]) -> list[str]:
    lines = []
    for idx, e in enumerate(events):
        key = e.key if e.key in _GLYPHS else repr(e.key)
        note = f"  {e.note}" if e.note else ""
        lines.append(f"{idx:5d}  {key:<10} +{e.delay_ms:6.0f} ms  hold {e.hold_ms:3.0f} ms{note}")
    return lines
