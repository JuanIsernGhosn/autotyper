"""Typing parameters, loaded from defaults, an optional YAML profile and CLI flags."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

import yaml

from autotyper.layouts import LAYOUTS


@dataclass
class TypingConfig:
    cps: float = 6.0
    speed_sigma: float = 0.35
    error_rate: float = 0.02
    uncorrected_rate: float = 0.0
    think_pause_rate: float = 0.03
    layout: str = "es"
    app_name: str = "Google Chrome"
    focus_guard: bool = True
    countdown: int = 5
    seed: int | None = None
    pause_key: str = "f8"
    abort_key: str = "esc"


_FIELD_NAMES = {f.name for f in fields(TypingConfig)}


def load_profile(path: str | Path) -> dict[str, Any]:
    """Read a YAML profile. An empty file yields an empty dict."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"profile {path} must be a mapping")
    return data


def merge(base: TypingConfig, overrides: Mapping[str, Any]) -> TypingConfig:
    """Return base with every non-None override applied, then validated.

    A ``wpm`` key is accepted as an alternative to ``cps`` (1 word = 5 chars).
    """
    overrides = dict(overrides)
    wpm = overrides.pop("wpm", None)
    if wpm is not None:
        if overrides.get("cps") is not None:
            raise ValueError("use either wpm or cps, not both")
        if wpm <= 0:
            raise ValueError("wpm must be > 0")
        overrides["cps"] = wpm * 5 / 60
    unknown = set(overrides) - _FIELD_NAMES
    if unknown:
        raise ValueError(f"unknown config keys: {', '.join(sorted(unknown))}")
    changes = {k: v for k, v in overrides.items() if v is not None}
    cfg = replace(base, **changes)
    _validate(cfg)
    return cfg


def _validate(cfg: TypingConfig) -> None:
    if cfg.cps <= 0:
        raise ValueError("cps must be > 0")
    if cfg.speed_sigma < 0:
        raise ValueError("speed_sigma must be >= 0")
    for name in ("error_rate", "uncorrected_rate", "think_pause_rate"):
        value = getattr(cfg, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if cfg.layout not in LAYOUTS:
        raise ValueError(f"layout must be one of: {', '.join(sorted(LAYOUTS))}")
    if cfg.countdown < 0:
        raise ValueError("countdown must be >= 0")
