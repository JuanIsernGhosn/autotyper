"""Execute planned events with pause, abort and focus guard."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from autotyper.events import Event
from autotyper.injector import Injector


@dataclass
class Controls:
    started: bool = False
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
    guard: Callable[[], str | None] | None = None,
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
            if not _wait_until_ready(controls, sleep, guard, log, poll_s):
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
    guard: Callable[[], str | None] | None,
    log: Callable[[str], None],
    poll_s: float,
) -> bool:
    """Block while paused or while the guard returns a reason to wait. False on abort.

    The guard returns None when typing may proceed, otherwise a short
    human-readable reason (e.g. which app is in front instead).
    """
    announced_pause = False
    announced_reason: str | None = None
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
        if guard is not None:
            reason = guard()
            if reason is not None:
                if announced_reason != reason:
                    log(f"\nauto-paused: {reason}")
                    announced_reason = reason
                sleep(poll_s)
                continue
            if announced_reason is not None:
                log("\nresumed")
                announced_reason = None
        return True
