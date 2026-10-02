"""Pick a typing speed so the whole text takes a target number of seconds."""

from __future__ import annotations

import random
from dataclasses import replace

from autotyper.config import TypingConfig
from autotyper.events import Event
from autotyper.model import plan

_MIN_CPS = 0.5
_MAX_CPS = 40.0


def fit_duration(
    text: str, config: TypingConfig, seed: int, target_s: float, rounds: int = 3
) -> tuple[list[Event], float]:
    """Re-plan a few times, scaling cps by measured/target, since pauses do not scale."""
    if target_s <= 0:
        raise ValueError("duration must be > 0")
    cps = config.cps
    for _ in range(rounds):
        events = plan(text, replace(config, cps=cps), random.Random(seed))
        total_s = sum(e.delay_ms for e in events) / 1000
        if total_s <= 0:
            break
        cps = min(_MAX_CPS, max(_MIN_CPS, cps * total_s / target_s))
    events = plan(text, replace(config, cps=cps), random.Random(seed))
    return events, cps
