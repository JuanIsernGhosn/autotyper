"""Execute planned events with pause, abort and focus guard."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from autotyper.events import Event
from autotyper.injector import Injector


@dataclass
class Controls:
    paused: bool = False
    aborted: bool = False


@dataclass(frozen=True)
class RunResult:
    pressed: int
    aborted: bool


def run(
    events: Sequence[Event],
    injector: Injector,
    controls: Controls,
    *,
    sleep: Callable[[float], None] = time.sleep,
    focus_check: Callable[[], str | None] | None = None,
    app_name: str | None = None,
    log: Callable[[str], None] = print,
    poll_s: float = 0.1,
    on_progress: Callable[[int, int, float], None] | None = None,
) -> RunResult:
    total = len(events)
    remaining = [0.0] * (total + 1)
    for i in range(total - 1, -1, -1):
        remaining[i] = remaining[i + 1] + events[i].delay_ms / 1000
    pressed = 0
    try:
        for event in events:
            if not _wait_until_ready(controls, sleep, focus_check, app_name, log, poll_s):
                return RunResult(pressed=pressed, aborted=True)
            sleep(event.delay_ms / 1000)
            if controls.aborted:
                return RunResult(pressed=pressed, aborted=True)
            injector.press(event.key, event.hold_ms / 1000)
            pressed += 1
            if on_progress is not None:
                on_progress(pressed, total, remaining[pressed])
    except KeyboardInterrupt:
        log("\ninterrupted")
        return RunResult(pressed=pressed, aborted=True)
    return RunResult(pressed=pressed, aborted=False)


def _wait_until_ready(
    controls: Controls,
    sleep: Callable[[float], None],
    focus_check: Callable[[], str | None] | None,
    app_name: str | None,
    log: Callable[[str], None],
    poll_s: float,
) -> bool:
    """Block while paused or while the target app is not in front. False on abort."""
    announced_pause = False
    announced_focus: str | None = None
    while True:
        if controls.aborted:
            return False
        if controls.paused:
            if not announced_pause:
                log("\npaused")
                announced_pause = True
            sleep(poll_s)
            continue
        if announced_pause:
            log("\nresumed")
            announced_pause = False
        if focus_check is not None and app_name:
            front = focus_check()
            if front is not None and front != app_name:
                if announced_focus != front:
                    log(f"\nauto-paused: {front!r} is in front, waiting for {app_name!r}")
                    announced_focus = front
                sleep(poll_s)
                continue
            if announced_focus is not None:
                log("\nresumed")
                announced_focus = None
        return True
