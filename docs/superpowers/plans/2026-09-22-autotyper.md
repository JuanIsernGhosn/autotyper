# autotyper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A macOS CLI that types a text into any Chrome input with human-like rhythm, typos and corrections, injecting real OS keystrokes.

**Architecture:** A pure planner (`model.py`) turns text into a list of timed `Event`s; a runner executes them through an `Injector` with pause/abort/focus-guard controls. Everything except the two thin OS adapters (`PynputInjector`, `focus.py`, `hotkeys.py`) is deterministic and unit-tested with a seeded `random.Random`.

**Tech Stack:** Python 3.12+, `uv`, `pynput`, `pyyaml`, `pyobjc-framework-Cocoa`, `pyobjc-framework-ApplicationServices`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-22-autotyper-design.md`

## Global Constraints

- Python `>=3.12`, managed with `uv`. Run tests with `uv run pytest`.
- Package layout: flat `autotyper/` package at repo root (not `src/`).
- Runtime deps only: `pynput`, `pyyaml`, `pyobjc-framework-Cocoa`, `pyobjc-framework-ApplicationServices` (the last two `sys_platform == 'darwin'` only).
- Special keys are the strings `"backspace"`, `"enter"`, `"tab"`; everything else in `Event.key` is a single character.
- All times in the planner are milliseconds (`float`); the injector and runner take seconds.
- Defaults: `cps=6.0`, `error_rate=0.02`, `uncorrected_rate=0.0`, `layout="es"`, `countdown=5`, `pause_key="f8"`, `abort_key="esc"`, `app_name="Google Chrome"`.
- Invariant: with `uncorrected_rate=0`, `replay(plan(text))` must equal `text` (after stripping `\r`).
- Commit after every task with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer.

---

## File structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, `autotyper` script entry point, pytest config |
| `autotyper/__init__.py` | Version string only |
| `autotyper/events.py` | `Event` dataclass, special key constants, `replay()` |
| `autotyper/layouts.py` | Neighbor-key tables for `es` and `us`, `neighbor()` |
| `autotyper/config.py` | `TypingConfig` dataclass, YAML loading, override merge |
| `autotyper/model.py` | `Planner` and `plan()`: rhythm, drift, pauses, typos, corrections |
| `autotyper/dryrun.py` | Transcript, summary and verbose rendering of an event list |
| `autotyper/injector.py` | `Injector` protocol, `RecordingInjector`, `PynputInjector` |
| `autotyper/focus.py` | `frontmost_app_name()`, `accessibility_trusted()` |
| `autotyper/runner.py` | `Controls`, `RunResult`, `run()` |
| `autotyper/hotkeys.py` | `key_name()`, `HotkeyListener` |
| `autotyper/cli.py` | `main()` argparse entry point |
| `tests/test_*.py` | One test file per module |
| `README.md` | Usage, permissions, hotkeys |

---

### Task 1: Project scaffold and `events.py`

**Files:**
- Create: `pyproject.toml`, `autotyper/__init__.py`, `autotyper/events.py`, `tests/__init__.py`, `tests/test_events.py`, `.gitignore`

**Interfaces:**
- Produces: `Event(key: str, delay_ms: float, hold_ms: float, note: str = "")` (frozen dataclass); constants `BACKSPACE = "backspace"`, `ENTER = "enter"`, `TAB = "tab"`, `SPECIAL_KEYS: frozenset[str]`; `replay(events: Iterable[Event]) -> str`.

- [ ] **Step 1: Create `pyproject.toml` and package init**

```toml
[project]
name = "autotyper"
version = "0.1.0"
description = "Type text into any input with human-like rhythm, typos and corrections."
requires-python = ">=3.12"
dependencies = [
    "pynput>=1.8",
    "pyyaml>=6",
    "pyobjc-framework-Cocoa>=10; sys_platform == 'darwin'",
    "pyobjc-framework-ApplicationServices>=10; sys_platform == 'darwin'",
]

[project.scripts]
autotyper = "autotyper.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["autotyper"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`autotyper/__init__.py`:

```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
dist/
```

- [ ] **Step 2: Write the failing test**

`tests/test_events.py`:

```python
from autotyper.events import BACKSPACE, ENTER, TAB, Event, replay


def test_replay_types_characters_in_order():
    events = [Event("h", 0, 50), Event("i", 0, 50)]
    assert replay(events) == "hi"


def test_replay_backspace_removes_last_char():
    events = [Event("h", 0, 50), Event("x", 0, 50), Event(BACKSPACE, 0, 50), Event("i", 0, 50)]
    assert replay(events) == "hi"


def test_replay_backspace_on_empty_buffer_is_noop():
    assert replay([Event(BACKSPACE, 0, 50), Event("a", 0, 50)]) == "a"


def test_replay_enter_and_tab_map_to_whitespace():
    events = [Event("a", 0, 50), Event(ENTER, 0, 50), Event(TAB, 0, 50), Event("b", 0, 50)]
    assert replay(events) == "a\n\tb"


def test_event_default_note_is_empty():
    assert Event("a", 1.0, 2.0).note == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv sync && uv run pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autotyper.events'`

- [ ] **Step 4: Write `autotyper/events.py`**

```python
"""Timed keystroke events produced by the planner and consumed by the runner."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

BACKSPACE = "backspace"
ENTER = "enter"
TAB = "tab"
SPECIAL_KEYS = frozenset({BACKSPACE, ENTER, TAB})


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
        elif e.key == ENTER:
            buf.append("\n")
        elif e.key == TAB:
            buf.append("\t")
        else:
            buf.append(e.key)
    return "".join(buf)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore autotyper tests
git commit -m "feat: scaffold package and add Event model with replay"
```

---

### Task 2: Keyboard layouts

**Files:**
- Create: `autotyper/layouts.py`, `tests/test_layouts.py`

**Interfaces:**
- Produces: `LAYOUTS: dict[str, dict[str, list[str]]]` (keys `"es"`, `"us"`; inner maps lowercase letter to list of lowercase neighbor letters); `neighbor(ch: str, layout: str, rng: random.Random) -> str | None` (preserves case; `None` when `ch` is not on the layout).

- [ ] **Step 1: Write the failing test**

`tests/test_layouts.py`:

```python
import random

import pytest

from autotyper.layouts import LAYOUTS, neighbor


@pytest.mark.parametrize("layout", ["es", "us"])
def test_every_key_has_letter_neighbors_that_exist_in_table(layout):
    table = LAYOUTS[layout]
    assert table, "layout table must not be empty"
    for key, neighbors in table.items():
        assert neighbors, f"{key!r} has no neighbors"
        for n in neighbors:
            assert n.isalpha()
            assert n in table


def test_es_layout_knows_enie():
    assert "ñ" in LAYOUTS["es"]
    assert "l" in LAYOUTS["es"]["ñ"]


def test_us_layout_has_no_enie():
    assert "ñ" not in LAYOUTS["us"]


def test_neighbor_returns_adjacent_key():
    rng = random.Random(1)
    for _ in range(50):
        assert neighbor("s", "es", rng) in LAYOUTS["es"]["s"]


def test_neighbor_preserves_upper_case():
    rng = random.Random(1)
    n = neighbor("S", "es", rng)
    assert n.isupper()
    assert n.lower() in LAYOUTS["es"]["s"]


def test_neighbor_returns_none_for_unknown_char():
    assert neighbor("á", "es", random.Random(1)) is None
    assert neighbor("3", "es", random.Random(1)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_layouts.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/layouts.py`**

```python
"""Physical neighbor tables used to pick plausible wrong keys."""

from __future__ import annotations

import random

# Rows as printed on the keyboard, left to right. Only letters end up in the
# tables, but non-letters are kept in the rows so column positions stay right.
_ES_ROWS = [
    "1234567890'¡",
    "qwertyuiop`+",
    "asdfghjklñ´ç",
    "zxcvbnm,.-",
]

_US_ROWS = [
    "1234567890-=",
    "qwertyuiop[]",
    "asdfghjkl;'",
    "zxcvbnm,./",
]


def _build(rows: list[str]) -> dict[str, list[str]]:
    """Map each letter to the letters physically around it.

    Rows are staggered half a key to the right as you go down, so the row
    above contributes columns c and c+1, and the row below c-1 and c.
    """
    table: dict[str, list[str]] = {}
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if not ch.isalpha():
                continue
            candidates: list[str] = []
            if c > 0:
                candidates.append(row[c - 1])
            if c + 1 < len(row):
                candidates.append(row[c + 1])
            if r > 0:
                above = rows[r - 1]
                candidates += [above[i] for i in (c, c + 1) if 0 <= i < len(above)]
            if r + 1 < len(rows):
                below = rows[r + 1]
                candidates += [below[i] for i in (c - 1, c) if 0 <= i < len(below)]
            letters = [x for x in candidates if x.isalpha()]
            if letters:
                table[ch] = letters
    return table


LAYOUTS: dict[str, dict[str, list[str]]] = {
    "es": _build(_ES_ROWS),
    "us": _build(_US_ROWS),
}


def neighbor(ch: str, layout: str, rng: random.Random) -> str | None:
    """Return a random adjacent letter with the same case as ch, or None."""
    options = LAYOUTS[layout].get(ch.lower())
    if not options:
        return None
    picked = rng.choice(options)
    return picked.upper() if ch.isupper() else picked
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_layouts.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/layouts.py tests/test_layouts.py
git commit -m "feat: add es/us neighbor-key layouts"
```

---

### Task 3: Configuration

**Files:**
- Create: `autotyper/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `TypingConfig` dataclass (fields and defaults as in the spec table); `load_profile(path: str | Path) -> dict[str, Any]`; `merge(base: TypingConfig, overrides: Mapping[str, Any]) -> TypingConfig` (skips `None` values, raises `ValueError` on unknown keys, validates `layout in LAYOUTS`, `cps > 0`, rates in `[0, 1]`).

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
import pytest

from autotyper.config import TypingConfig, load_profile, merge


def test_defaults_match_spec():
    c = TypingConfig()
    assert c.cps == 6.0
    assert c.speed_sigma == 0.35
    assert c.error_rate == 0.02
    assert c.uncorrected_rate == 0.0
    assert c.think_pause_rate == 0.03
    assert c.layout == "es"
    assert c.app_name == "Google Chrome"
    assert c.focus_guard is True
    assert c.countdown == 5
    assert c.seed is None
    assert c.pause_key == "f8"
    assert c.abort_key == "esc"


def test_merge_overrides_only_non_none_values():
    c = merge(TypingConfig(), {"cps": 9.0, "error_rate": None, "layout": "us"})
    assert c.cps == 9.0
    assert c.error_rate == 0.02
    assert c.layout == "us"


def test_merge_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown"):
        merge(TypingConfig(), {"speed": 3})


@pytest.mark.parametrize(
    "overrides",
    [{"cps": 0}, {"cps": -1}, {"error_rate": 1.5}, {"uncorrected_rate": -0.1}, {"layout": "fr"}],
)
def test_merge_validates_values(overrides):
    with pytest.raises(ValueError):
        merge(TypingConfig(), overrides)


def test_load_profile_reads_yaml(tmp_path):
    p = tmp_path / "perfil.yaml"
    p.write_text("cps: 4.5\nlayout: us\nseed: 7\n")
    assert load_profile(p) == {"cps": 4.5, "layout": "us", "seed": 7}


def test_load_profile_empty_file_is_empty_dict(tmp_path):
    p = tmp_path / "perfil.yaml"
    p.write_text("")
    assert load_profile(p) == {}


def test_profile_then_cli_precedence(tmp_path):
    p = tmp_path / "perfil.yaml"
    p.write_text("cps: 4.5\nlayout: us\n")
    c = merge(merge(TypingConfig(), load_profile(p)), {"cps": 8.0, "layout": None})
    assert c.cps == 8.0
    assert c.layout == "us"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/config.py`**

```python
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
    """Return base with every non-None override applied, then validated."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/config.py tests/test_config.py
git commit -m "feat: add TypingConfig with YAML profile and override merge"
```

---

### Task 4: Planner rhythm (no typos yet)

**Files:**
- Create: `autotyper/model.py`, `tests/test_model.py`

**Interfaces:**
- Consumes: `Event`, `ENTER`, `TAB`, `BACKSPACE` from `events.py`; `TypingConfig`; `neighbor` from `layouts.py`.
- Produces: `plan(text: str, config: TypingConfig, rng: random.Random) -> list[Event]`; class `Planner(config, rng)` with method `plan(text) -> list[Event]`. Task 5 adds `Planner._typo`.

- [ ] **Step 1: Write the failing tests**

`tests/test_model.py`:

```python
import random

from autotyper.config import TypingConfig
from autotyper.events import BACKSPACE, ENTER, TAB, replay
from autotyper.model import plan


def cfg(**kw):
    base = {"error_rate": 0.0, "think_pause_rate": 0.0}
    base.update(kw)
    return TypingConfig(**base)


def test_plan_without_errors_reproduces_text():
    text = "Hola, mundo. ¿Qué tal?\nBien."
    events = plan(text, cfg(), random.Random(1))
    assert replay(events) == text
    assert all(e.key != BACKSPACE for e in events)


def test_plan_is_deterministic_for_a_seed():
    a = plan("hola mundo", cfg(), random.Random(3))
    b = plan("hola mundo", cfg(), random.Random(3))
    assert a == b


def test_newline_and_tab_become_special_keys_and_cr_is_dropped():
    events = plan("a\r\n\tb", cfg(), random.Random(1))
    assert [e.key for e in events] == ["a", ENTER, TAB, "b"]


def test_effective_cps_is_near_configured():
    text = "lorem ipsum dolor sit amet " * 40
    events = plan(text, cfg(cps=6.0), random.Random(5))
    seconds = sum(e.delay_ms for e in events) / 1000
    effective = len(text) / seconds
    assert 0.6 * 6.0 <= effective <= 1.6 * 6.0


def test_hold_is_within_bounds_and_delays_are_positive():
    events = plan("abc def", cfg(), random.Random(2))
    for e in events:
        assert 25 <= e.hold_ms <= 120
        assert e.delay_ms > 0


def test_pause_after_sentence_end_is_longer_than_after_letter():
    rng = random.Random(9)
    events = plan("a. b", cfg(), rng)
    # events: a . space b -> the space carries the post-period pause
    assert events[2].delay_ms >= 300


def test_pause_after_newline_is_longest():
    events = plan("a\nb", cfg(), random.Random(9))
    assert events[2].delay_ms >= 500


def test_think_pause_can_happen_at_word_start():
    events = plan("uno dos tres", cfg(think_pause_rate=1.0), random.Random(1))
    # "dos" starts at index 4, "tres" at index 8
    assert events[4].delay_ms >= 800
    assert events[8].delay_ms >= 800
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/model.py` (rhythm only)**

```python
"""Turn text into human-looking timed keystrokes."""

from __future__ import annotations

import math
import random

from autotyper.config import TypingConfig
from autotyper.events import BACKSPACE, ENTER, TAB, Event
from autotyper.layouts import neighbor

_PUNCT_SHORT = frozenset(",;:")
_PUNCT_LONG = frozenset(".!?…")

_CTX_UPPER = 1.4
_CTX_DIGIT = 1.3
_CTX_SYMBOL = 1.3
_CTX_AFTER_FIX = 1.2
_SLOW_KEYS_AFTER_FIX = 3


class Planner:
    def __init__(self, config: TypingConfig, rng: random.Random) -> None:
        self.cfg = config
        self.rng = rng
        self.base_ms = 1000.0 / config.cps
        self.drift = 1.0
        self.slow_after_fix = 0
        self.pending_pause_ms = 0.0
        self.events: list[Event] = []

    # -- public -----------------------------------------------------------

    def plan(self, text: str) -> list[Event]:
        text = text.replace("\r", "")
        i = 0
        at_word_start = True
        while i < len(text):
            ch = text[i]
            if at_word_start and not ch.isspace():
                if self.rng.random() < self.cfg.think_pause_rate:
                    self.pending_pause_ms += self.rng.uniform(800, 2500)
            if ch.isalpha() and self.rng.random() < self.cfg.error_rate:
                i = self._typo(text, i)
                at_word_start = False
            else:
                self._emit_char(ch)
                at_word_start = ch.isspace()
                i += 1
        return self.events

    # -- timing helpers ---------------------------------------------------

    def _hold_ms(self) -> float:
        return min(120.0, max(25.0, self.rng.gauss(60, 15)))

    def _tick_drift(self) -> None:
        self.drift += 0.02 * (1.0 - self.drift) + self.rng.gauss(0, 0.05)
        self.drift = min(1.6, max(0.6, self.drift))

    def _ctx(self, ch: str) -> float:
        if ch.isupper():
            return _CTX_UPPER
        if ch.isdigit():
            return _CTX_DIGIT
        if not ch.isalnum() and not ch.isspace():
            return _CTX_SYMBOL
        return 1.0

    def _take_pending(self) -> float:
        p = self.pending_pause_ms
        self.pending_pause_ms = 0.0
        return p

    # -- emitters ---------------------------------------------------------

    def _emit_char(self, ch: str, note: str = "") -> None:
        ctx = self._ctx(ch)
        if self.slow_after_fix > 0:
            ctx *= _CTX_AFTER_FIX
            self.slow_after_fix -= 1
        self._tick_drift()
        jitter = math.exp(self.rng.gauss(0, self.cfg.speed_sigma))
        delay = self.base_ms * self.drift * ctx * jitter + self._take_pending()
        key = ENTER if ch == "\n" else TAB if ch == "\t" else ch
        self.events.append(Event(key, delay, self._hold_ms(), note))
        if ch in _PUNCT_SHORT:
            self.pending_pause_ms += self.rng.uniform(150, 400)
        elif ch in _PUNCT_LONG:
            self.pending_pause_ms += self.rng.uniform(300, 900)
        elif ch == "\n":
            self.pending_pause_ms += self.rng.uniform(500, 1500)

    def _emit_backspace(self) -> None:
        delay = self.rng.uniform(80, 140) + self._take_pending()
        self.events.append(Event(BACKSPACE, delay, self._hold_ms(), "fix"))

    # -- typos (Task 5) ---------------------------------------------------

    def _typo(self, text: str, i: int) -> int:
        raise NotImplementedError


def plan(text: str, config: TypingConfig, rng: random.Random) -> list[Event]:
    return Planner(config, rng).plan(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/model.py tests/test_model.py
git commit -m "feat: add planner with rhythm, drift and contextual pauses"
```

---

### Task 5: Typos and corrections

**Files:**
- Modify: `autotyper/model.py` (replace `_typo`)
- Modify: `tests/test_model.py` (append tests)

**Interfaces:**
- Consumes: `Planner` from Task 4, `neighbor()` from Task 2.
- Produces: `Planner._typo(text: str, i: int) -> int` returning the next index to process. Error events carry `note="error:<kind>"` with kind in `neighbor`, `transpose`, `double`, `omit`; corrections carry `note="fix"`.

- [ ] **Step 1: Append failing tests to `tests/test_model.py`**

```python
from autotyper.layouts import LAYOUTS


def test_plan_with_errors_still_reproduces_text_when_all_corrected():
    text = "Ayer fui al mercado y compré manzanas, peras y ñoras.\nLuego volví a casa."
    for seed in range(30):
        events = plan(text, cfg(error_rate=0.3), random.Random(seed))
        assert replay(events) == text, f"seed {seed}"


def test_high_error_rate_produces_backspaces_and_error_notes():
    events = plan("abcdefghij klmnopqrst", cfg(error_rate=1.0), random.Random(1))
    assert any(e.key == BACKSPACE for e in events)
    kinds = {e.note for e in events if e.note.startswith("error:")}
    assert kinds <= {"error:neighbor", "error:transpose", "error:double", "error:omit"}
    assert kinds


def test_all_four_error_kinds_show_up_over_many_seeds():
    seen = set()
    for seed in range(40):
        events = plan("hola mundo cruel", cfg(error_rate=1.0), random.Random(seed))
        seen |= {e.note for e in events if e.note.startswith("error:")}
    assert seen == {"error:neighbor", "error:transpose", "error:double", "error:omit"}


def test_neighbor_errors_come_from_layout_table():
    text = "sdfg" * 20
    events = plan(text, cfg(error_rate=1.0), random.Random(4))
    wrong = [e for e in events if e.note == "error:neighbor"]
    assert wrong
    for e in wrong:
        # the intended letter is unknown here, so check the wrong key is a
        # neighbor of at least one of the letters in the text
        assert any(e.key.lower() in LAYOUTS["es"][c] for c in "sdfg")


def test_uncorrected_errors_change_final_text():
    text = "abcdefghijklmnopqrstuvwxyz" * 3
    events = plan(text, cfg(error_rate=1.0, uncorrected_rate=1.0), random.Random(2))
    assert replay(events) != text
    assert all(e.key != BACKSPACE for e in events)


def test_correction_does_not_cross_word_boundary():
    # With k up to 3 extra chars, a typo on "ab" can only ever backspace the
    # current word, never the space before it.
    for seed in range(30):
        events = plan("xy ab cd", cfg(error_rate=1.0), random.Random(seed))
        assert replay(events) == "xy ab cd"
        typed = ""
        for e in events:
            if e.key == BACKSPACE:
                assert typed[-1] != " ", "backspaced over a space"
                typed = typed[:-1]
            else:
                typed += e.key


def test_correction_has_reaction_pause_before_first_backspace():
    events = plan("abcdef", cfg(error_rate=1.0), random.Random(1))
    first_bs = next(e for e in events if e.key == BACKSPACE)
    assert first_bs.delay_ms >= 200


def test_accented_letters_never_use_neighbor_kind():
    events = plan("ááááá ééééé", cfg(error_rate=1.0), random.Random(1))
    assert not any(e.note == "error:neighbor" for e in events)
    assert replay(events) == "ááááá ééééé"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_model.py -v`
Expected: new tests FAIL with `NotImplementedError`

- [ ] **Step 3: Replace `_typo` in `autotyper/model.py`**

```python
    # -- typos ------------------------------------------------------------

    _ERROR_KINDS = ("neighbor", "transpose", "double", "omit")
    _ERROR_WEIGHTS = (0.50, 0.20, 0.15, 0.15)

    def _typo(self, text: str, i: int) -> int:
        """Emit a mistyped chunk starting at text[i], maybe fix it, return next index."""
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        kind = self.rng.choices(self._ERROR_KINDS, self._ERROR_WEIGHTS)[0]

        if kind == "transpose" and not nxt.isalpha():
            kind = "neighbor"
        wrong_ch = None
        if kind == "neighbor":
            wrong_ch = neighbor(ch, self.cfg.layout, self.rng)
            if wrong_ch is None:
                kind = "double"

        if kind == "neighbor":
            wrong, correct, advance = [wrong_ch], [ch], 1
        elif kind == "transpose":
            wrong, correct, advance = [nxt, ch], [ch, nxt], 2
        elif kind == "double":
            wrong, correct, advance = [ch, ch], [ch], 1
        else:  # omit
            wrong, correct, advance = [], [ch], 1

        k = 0 if self.rng.random() < 0.5 else self.rng.randint(1, 3)
        if kind == "omit" and k == 0:
            k = 1
        j = i + advance
        extra: list[str] = []
        while len(extra) < k and j < len(text) and not text[j].isspace():
            extra.append(text[j])
            j += 1
        if kind == "omit" and not extra:
            kind, wrong = "double", [ch, ch]

        for w in wrong:
            self._emit_char(w, note=f"error:{kind}")
        for x in extra:
            self._emit_char(x)

        if self.rng.random() < self.cfg.uncorrected_rate:
            return j

        self.pending_pause_ms = self.rng.uniform(200, 500)
        for _ in range(len(wrong) + len(extra)):
            self._emit_backspace()
        self.slow_after_fix = _SLOW_KEYS_AFTER_FIX
        for c in correct:
            self._emit_char(c, note="fix")
        for x in extra:
            self._emit_char(x, note="fix")
        return j
```

Also remove the `raise NotImplementedError` stub and its comment.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/model.py tests/test_model.py
git commit -m "feat: add typo injection with delayed corrections"
```

---

### Task 6: Dry-run rendering

**Files:**
- Create: `autotyper/dryrun.py`, `tests/test_dryrun.py`

**Interfaces:**
- Consumes: `Event`, `BACKSPACE`, `ENTER`, `TAB`, `replay`.
- Produces: `transcript(events) -> str` (typed keys in order, `⌫` for backspace, `⏎\n` for enter, `⇥` for tab); `summary(events) -> str` (multi-line: total seconds, chars in final text, error count, effective cps); `verbose_lines(events) -> list[str]` (one line per event: index, key repr, delay, hold, note).

- [ ] **Step 1: Write the failing test**

`tests/test_dryrun.py`:

```python
import random

from autotyper.config import TypingConfig
from autotyper.dryrun import summary, transcript, verbose_lines
from autotyper.events import BACKSPACE, ENTER, TAB, Event
from autotyper.model import plan


def test_transcript_of_clean_plan_is_the_text():
    text = "hola mundo"
    events = plan(text, TypingConfig(error_rate=0.0, think_pause_rate=0.0), random.Random(1))
    assert transcript(events) == text


def test_transcript_renders_special_keys():
    events = [Event("a", 0, 50), Event("x", 0, 50), Event(BACKSPACE, 0, 50), Event(ENTER, 0, 50), Event(TAB, 0, 50)]
    assert transcript(events) == "ax⌫⏎\n⇥"


def test_summary_reports_duration_errors_and_cps():
    events = [
        Event("a", 500, 50),
        Event("x", 500, 50, "error:neighbor"),
        Event(BACKSPACE, 300, 50, "fix"),
        Event("b", 700, 50, "fix"),
    ]
    out = summary(events)
    assert "2.0 s" in out
    assert "errors: 1" in out
    assert "chars: 2" in out
    assert "cps: 1.0" in out


def test_verbose_lines_one_per_event_with_note():
    events = [Event("a", 120.4, 55.5), Event(BACKSPACE, 90, 60, "fix")]
    lines = verbose_lines(events)
    assert len(lines) == 2
    assert "'a'" in lines[0] and "120" in lines[0] and "56" in lines[0]
    assert "backspace" in lines[1] and "fix" in lines[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dryrun.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/dryrun.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dryrun.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/dryrun.py tests/test_dryrun.py
git commit -m "feat: add dry-run transcript and summary"
```

---

### Task 7: Injector and focus adapters

**Files:**
- Create: `autotyper/injector.py`, `autotyper/focus.py`, `tests/test_injector.py`

**Interfaces:**
- Produces: `Injector` protocol with `press(key: str, hold_s: float) -> None`; `RecordingInjector` with `.pressed: list[tuple[str, float]]`; `PynputInjector` (real); `frontmost_app_name() -> str | None`; `accessibility_trusted() -> bool | None`.

- [ ] **Step 1: Write the failing test**

`tests/test_injector.py`:

```python
from autotyper.injector import PynputInjector, RecordingInjector


def test_recording_injector_stores_presses():
    inj = RecordingInjector()
    inj.press("a", 0.05)
    inj.press("backspace", 0.06)
    assert inj.pressed == [("a", 0.05), ("backspace", 0.06)]


class FakeKeyboard:
    def __init__(self):
        self.log = []

    def press(self, k):
        self.log.append(("down", k))

    def release(self, k):
        self.log.append(("up", k))


def test_pynput_injector_maps_special_keys_and_holds():
    kb = FakeKeyboard()
    sleeps = []
    inj = PynputInjector(keyboard=kb, special={"backspace": "BS"}, sleep=sleeps.append)
    inj.press("backspace", 0.04)
    inj.press("ñ", 0.05)
    assert kb.log == [("down", "BS"), ("up", "BS"), ("down", "ñ"), ("up", "ñ")]
    assert sleeps == [0.04, 0.05]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_injector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/injector.py`**

```python
"""Key injection back ends."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

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
```

- [ ] **Step 4: Write `autotyper/focus.py`**

```python
"""macOS helpers: which app is in front, and whether we may inject keys."""

from __future__ import annotations


def frontmost_app_name() -> str | None:
    """Localized name of the frontmost app, or None if unavailable."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return str(app.localizedName()) if app is not None else None


def accessibility_trusted() -> bool | None:
    """True/False from AXIsProcessTrusted, or None if the API is unavailable."""
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return None
    return bool(AXIsProcessTrusted())
```

- [ ] **Step 5: Run tests and a manual smoke check of focus.py**

Run: `uv run pytest tests/test_injector.py -v`
Expected: all passed

Run: `uv run python -c "from autotyper.focus import frontmost_app_name, accessibility_trusted; print(frontmost_app_name(), accessibility_trusted())"`
Expected: prints an app name (e.g. `Code`) and `True` or `False`, no traceback. If `ApplicationServices` import fails, check the installed pyobjc package name with `uv pip list | grep -i pyobjc` and adjust the import.

- [ ] **Step 6: Commit**

```bash
git add autotyper/injector.py autotyper/focus.py tests/test_injector.py
git commit -m "feat: add pynput injector and macOS focus helpers"
```

---

### Task 8: Runner with pause, abort and focus guard

**Files:**
- Create: `autotyper/runner.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `Event`, `Injector`.
- Produces: `Controls` dataclass (`paused: bool = False`, `aborted: bool = False`); `RunResult(pressed: int, aborted: bool)`; `run(events, injector, controls, *, sleep=time.sleep, focus_check=None, app_name=None, log=print, poll_s=0.1) -> RunResult`.

- [ ] **Step 1: Write the failing test**

`tests/test_runner.py`:

```python
from autotyper.events import Event
from autotyper.injector import RecordingInjector
from autotyper.runner import Controls, RunResult, run

EVENTS = [Event("a", 100, 50), Event("b", 200, 60), Event("c", 300, 70)]


def test_run_presses_every_key_in_order_and_sleeps_delays():
    inj = RecordingInjector()
    sleeps = []
    result = run(EVENTS, inj, Controls(), sleep=sleeps.append)
    assert result == RunResult(pressed=3, aborted=False)
    assert inj.pressed == [("a", 0.05), ("b", 0.06), ("c", 0.07)]
    assert sleeps == [0.1, 0.2, 0.3]


def test_abort_stops_before_next_key():
    inj = RecordingInjector()
    controls = Controls()

    def sleep(_):
        controls.aborted = True

    result = run(EVENTS, inj, controls, sleep=sleep)
    assert result.aborted is True
    assert inj.pressed == []


def test_pause_holds_without_losing_events():
    inj = RecordingInjector()
    controls = Controls(paused=True)
    polls = {"n": 0}

    def sleep(_):
        polls["n"] += 1
        if polls["n"] == 3:
            controls.paused = False

    result = run(EVENTS, inj, controls, sleep=sleep, poll_s=0.01)
    assert result.pressed == 3
    assert [k for k, _ in inj.pressed] == ["a", "b", "c"]
    assert polls["n"] >= 3


def test_focus_guard_pauses_until_app_returns():
    inj = RecordingInjector()
    front = ["Finder", "Finder", "Google Chrome"]
    logs = []
    result = run(
        EVENTS[:1],
        inj,
        Controls(),
        sleep=lambda _: None,
        focus_check=lambda: front.pop(0) if len(front) > 1 else front[0],
        app_name="Google Chrome",
        log=logs.append,
    )
    assert result.pressed == 1
    assert any("Finder" in line for line in logs)


def test_focus_guard_ignored_when_check_returns_none():
    inj = RecordingInjector()
    result = run(EVENTS, inj, Controls(), sleep=lambda _: None, focus_check=lambda: None, app_name="Google Chrome")
    assert result.pressed == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/runner.py`**

```python
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
) -> RunResult:
    for idx, event in enumerate(events):
        if not _wait_until_ready(controls, sleep, focus_check, app_name, log, poll_s):
            return RunResult(pressed=idx, aborted=True)
        sleep(event.delay_ms / 1000)
        if controls.aborted:
            return RunResult(pressed=idx, aborted=True)
        injector.press(event.key, event.hold_ms / 1000)
    return RunResult(pressed=len(events), aborted=False)


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
                log("paused")
                announced_pause = True
            sleep(poll_s)
            continue
        if announced_pause:
            log("resumed")
            announced_pause = False
        if focus_check is not None and app_name:
            front = focus_check()
            if front is not None and front != app_name:
                if announced_focus != front:
                    log(f"auto-paused: {front!r} is in front, waiting for {app_name!r}")
                    announced_focus = front
                sleep(poll_s)
                continue
            if announced_focus is not None:
                log("resumed")
                announced_focus = None
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runner.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/runner.py tests/test_runner.py
git commit -m "feat: add runner with pause, abort and focus guard"
```

---

### Task 9: Global hotkeys

**Files:**
- Create: `autotyper/hotkeys.py`, `tests/test_hotkeys.py`

**Interfaces:**
- Consumes: `Controls`.
- Produces: `key_name(key) -> str` (pynput `Key.f8` gives `"f8"`, `KeyCode('a')` gives `"a"`, else `""`); `HotkeyListener(controls, pause_key="f8", abort_key="esc", log=print)` with `.start()`, `.stop()`, `.on_press(key)`.

- [ ] **Step 1: Write the failing test**

`tests/test_hotkeys.py`:

```python
from types import SimpleNamespace

from autotyper.hotkeys import HotkeyListener, key_name
from autotyper.runner import Controls


def named(name):
    return SimpleNamespace(name=name)


def charkey(c):
    return SimpleNamespace(char=c)


def test_key_name_handles_named_and_char_keys():
    assert key_name(named("f8")) == "f8"
    assert key_name(charkey("a")) == "a"
    assert key_name(SimpleNamespace()) == ""
    assert key_name(SimpleNamespace(char=None)) == ""


def test_pause_key_toggles_and_abort_key_sets():
    controls = Controls()
    logs = []
    hk = HotkeyListener(controls, pause_key="f8", abort_key="esc", log=logs.append)
    hk.on_press(named("f8"))
    assert controls.paused is True
    hk.on_press(named("f8"))
    assert controls.paused is False
    hk.on_press(named("esc"))
    assert controls.aborted is True
    assert logs


def test_other_keys_are_ignored():
    controls = Controls()
    hk = HotkeyListener(controls, log=lambda _: None)
    hk.on_press(charkey("x"))
    assert controls == Controls()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hotkeys.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/hotkeys.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hotkeys.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add autotyper/hotkeys.py tests/test_hotkeys.py
git commit -m "feat: add global pause/abort hotkeys"
```

---

### Task 10: CLI and README

**Files:**
- Create: `autotyper/cli.py`, `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `build_parser() -> argparse.ArgumentParser`; `main(argv: list[str] | None = None) -> int`. Exit codes: 0 ok, 1 input/config error, 2 missing accessibility permission, 130 aborted.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:

```python
import pytest

from autotyper import cli


def test_dry_run_prints_transcript_and_summary(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("hola mundo")
    code = cli.main([str(f), "--dry-run", "--seed", "1", "--error-rate", "0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "hola mundo" in out
    assert "duration:" in out


def test_dry_run_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("desde stdin"))
    code = cli.main(["-", "--dry-run", "--seed", "1", "--error-rate", "0"])
    assert code == 0
    assert "desde stdin" in capsys.readouterr().out


def test_dry_run_verbose_lists_events(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    cli.main([str(f), "--dry-run", "--verbose", "--seed", "1", "--error-rate", "0"])
    out = capsys.readouterr().out
    assert "'a'" in out and "'b'" in out and "hold" in out


def test_missing_file_returns_1(capsys):
    assert cli.main(["/no/such/file.txt", "--dry-run"]) == 1
    assert "not found" in capsys.readouterr().err


def test_empty_text_returns_1(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("   \n")
    assert cli.main([str(f), "--dry-run"]) == 1
    assert "empty" in capsys.readouterr().err


def test_profile_and_flags_combine(tmp_path, capsys):
    prof = tmp_path / "p.yaml"
    prof.write_text("cps: 2\nerror_rate: 0\nthink_pause_rate: 0\n")
    f = tmp_path / "t.txt"
    f.write_text("a" * 20)
    cli.main([str(f), "--dry-run", "--profile", str(prof), "--seed", "1", "--cps", "20"])
    out = capsys.readouterr().out
    # 20 chars at 20 cps is about 1 s, not 10 s
    line = next(l for l in out.splitlines() if l.startswith("duration:"))
    seconds = float(line.split()[1])
    assert seconds < 3


def test_invalid_config_returns_1(tmp_path, capsys):
    f = tmp_path / "t.txt"
    f.write_text("hola")
    assert cli.main([str(f), "--dry-run", "--layout", "fr"]) == 1
    assert "layout" in capsys.readouterr().err


def test_real_run_uses_injected_dependencies(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    pressed = []

    class FakeInjector:
        def press(self, key, hold_s):
            pressed.append(key)

    class FakeHotkeys:
        def __init__(self, *a, **k):
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            pass

    monkeypatch.setattr(cli, "PynputInjector", FakeInjector)
    monkeypatch.setattr(cli, "HotkeyListener", FakeHotkeys)
    monkeypatch.setattr(cli, "accessibility_trusted", lambda: True)
    monkeypatch.setattr(cli, "frontmost_app_name", lambda: "Google Chrome")
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    code = cli.main([str(f), "--seed", "1", "--error-rate", "0", "--countdown", "0"])
    assert code == 0
    assert pressed == ["a", "b"]
    assert "done" in capsys.readouterr().out


def test_real_run_without_accessibility_returns_2(tmp_path, monkeypatch, capsys):
    f = tmp_path / "t.txt"
    f.write_text("ab")
    monkeypatch.setattr(cli, "accessibility_trusted", lambda: False)
    assert cli.main([str(f), "--countdown", "0"]) == 2
    assert "Accessibility" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `autotyper/cli.py`**

```python
"""Command-line entry point."""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from autotyper import __version__
from autotyper.config import TypingConfig, load_profile, merge
from autotyper.dryrun import summary, transcript, verbose_lines
from autotyper.focus import accessibility_trusted, frontmost_app_name
from autotyper.hotkeys import HotkeyListener
from autotyper.injector import PynputInjector
from autotyper.model import plan
from autotyper.runner import Controls, run

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_PERMISSION = 2
EXIT_ABORTED = 130


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="autotyper",
        description="Type a text into the focused input with human-like rhythm, typos and corrections.",
    )
    p.add_argument("text", help="path to a text file, or - for stdin")
    p.add_argument("--profile", help="YAML profile with config values")
    p.add_argument("--cps", type=float, help="characters per second (default 6)")
    p.add_argument("--speed-sigma", type=float, dest="speed_sigma", help="per-key jitter (default 0.35)")
    p.add_argument("--error-rate", type=float, dest="error_rate", help="typo probability per letter (default 0.02)")
    p.add_argument("--uncorrected-rate", type=float, dest="uncorrected_rate", help="share of typos left unfixed (default 0)")
    p.add_argument("--think-pause-rate", type=float, dest="think_pause_rate", help="long pause probability per word (default 0.03)")
    p.add_argument("--layout", choices=["es", "us"], help="keyboard layout for neighbor typos (default es)")
    p.add_argument("--app", dest="app_name", help='app that must be in front (default "Google Chrome")')
    p.add_argument("--no-focus-guard", action="store_true", help="do not auto-pause when the app loses focus")
    p.add_argument("--countdown", type=int, help="seconds to wait before typing (default 5)")
    p.add_argument("--seed", type=int, help="random seed for reproducible runs")
    p.add_argument("--pause-key", dest="pause_key", help="global pause/resume key (default f8)")
    p.add_argument("--abort-key", dest="abort_key", help="global abort key (default esc)")
    p.add_argument("--dry-run", action="store_true", help="print what would be typed, inject nothing")
    p.add_argument("--verbose", action="store_true", help="with --dry-run, list every keystroke")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _read_text(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {source}")
    return path.read_text(encoding="utf-8")


def _build_config(args: argparse.Namespace) -> TypingConfig:
    cfg = TypingConfig()
    if args.profile:
        cfg = merge(cfg, load_profile(args.profile))
    overrides = {
        "cps": args.cps,
        "speed_sigma": args.speed_sigma,
        "error_rate": args.error_rate,
        "uncorrected_rate": args.uncorrected_rate,
        "think_pause_rate": args.think_pause_rate,
        "layout": args.layout,
        "app_name": args.app_name,
        "focus_guard": False if args.no_focus_guard else None,
        "countdown": args.countdown,
        "seed": args.seed,
        "pause_key": args.pause_key,
        "abort_key": args.abort_key,
    }
    return merge(cfg, overrides)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = _read_text(args.text)
        if not text.strip():
            raise ValueError("text is empty")
        cfg = _build_config(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT

    seed = cfg.seed if cfg.seed is not None else random.randrange(2**32)
    events = plan(text, cfg, random.Random(seed))

    if args.dry_run:
        print(transcript(events))
        print()
        if args.verbose:
            print("\n".join(verbose_lines(events)))
            print()
        print(summary(events))
        print(f"seed: {seed}")
        return EXIT_OK

    if accessibility_trusted() is False:
        print(
            "error: this process is not allowed to control the keyboard.\n"
            "Enable it in System Settings > Privacy & Security > Accessibility "
            "for your terminal app (and Input Monitoring for the hotkeys), then retry.",
            file=sys.stderr,
        )
        return EXIT_PERMISSION

    controls = Controls()
    hotkeys = HotkeyListener(controls, cfg.pause_key, cfg.abort_key)
    hotkeys.start()
    try:
        print(f"seed: {seed}   pause: {cfg.pause_key}   abort: {cfg.abort_key}")
        for remaining in range(cfg.countdown, 0, -1):
            print(f"typing in {remaining}... click the target input now", flush=True)
            time.sleep(1)
        result = run(
            events,
            PynputInjector(),
            controls,
            focus_check=frontmost_app_name if cfg.focus_guard else None,
            app_name=cfg.app_name,
        )
    finally:
        hotkeys.stop()

    typed = sum(1 for e in events[: result.pressed] if e.key != "backspace")
    if result.aborted:
        print(f"aborted after {result.pressed} keystrokes ({typed} characters)")
        return EXIT_ABORTED
    print(f"done: {result.pressed} keystrokes")
    print(summary(events))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: all passed

- [ ] **Step 5: Write `README.md`**

```markdown
# autotyper

Escribe un texto en el input que tenga el foco (por ejemplo un campo de Chrome
que bloquea el pegado) imitando a una persona: velocidad variable, pausas tras
puntuación, errores de tecleo y sus correcciones. Inyecta pulsaciones reales a
nivel de sistema, así que para la página son indistinguibles de un teclado.

Solo macOS.

## Instalación

```sh
uv sync
```

## Permisos

En Ajustes del Sistema > Privacidad y seguridad:

- **Accesibilidad**: la app desde la que ejecutas el comando (Terminal, iTerm,
  VS Code...). Sin esto no se inyectan teclas.
- **Monitorización de entrada**: la misma app, para los atajos globales de
  pausa y aborto.

## Uso

```sh
# previsualizar sin escribir nada
uv run autotyper texto.txt --dry-run
uv run autotyper texto.txt --dry-run --verbose

# escribir de verdad: cuenta atrás de 5 s para hacer clic en el input
uv run autotyper texto.txt
uv run autotyper texto.txt --cps 8 --error-rate 0.03 --seed 42
cat texto.txt | uv run autotyper -

# perfil YAML (los flags de CLI tienen prioridad)
uv run autotyper texto.txt --profile perfil.yaml
```

Ejemplo de `perfil.yaml`:

```yaml
cps: 7
error_rate: 0.025
uncorrected_rate: 0.1
think_pause_rate: 0.04
layout: es
```

## Durante la escritura

- **F8** pausa y reanuda. **Esc** aborta. Ambos son globales: no hace falta
  volver a la terminal.
- Si Google Chrome deja de estar en primer plano, la escritura se pausa sola y
  continúa cuando vuelve. Cambia la app con `--app` o desactívalo con
  `--no-focus-guard`.
- La terminal debería estar en una pantalla que no se grabe.

## Parámetros

| Flag | Defecto | Qué hace |
|---|---|---|
| `--cps` | 6 | caracteres por segundo medios |
| `--speed-sigma` | 0.35 | dispersión del intervalo entre teclas |
| `--error-rate` | 0.02 | probabilidad de error por letra |
| `--uncorrected-rate` | 0 | fracción de errores que se dejan sin corregir |
| `--think-pause-rate` | 0.03 | probabilidad de pausa larga al empezar palabra |
| `--layout` | es | distribución para errores de tecla vecina (`es`, `us`) |
| `--countdown` | 5 | segundos antes de empezar |
| `--seed` | aleatorio | semilla para repetir una ejecución |

## Tests

```sh
uv run pytest
```
```

- [ ] **Step 6: Manual smoke test**

Run: `printf 'Hola, mundo. Esto es una prueba.\n' > /tmp/autotyper-smoke.txt && uv run autotyper /tmp/autotyper-smoke.txt --dry-run --seed 1 --error-rate 0.2`
Expected: a transcript with some `⌫`, then a summary block and `seed: 1`.

Run: `uv run autotyper --help`
Expected: usage text, exit 0.

- [ ] **Step 7: Commit**

```bash
git add autotyper/cli.py tests/test_cli.py README.md
git commit -m "feat: add CLI with dry-run, countdown, hotkeys and focus guard"
```

---

## Self-review

**Spec coverage:** events/replay (T1), layouts es/us (T2), config + YAML + precedence (T3), rhythm, drift, ctx multipliers, pauses, hold (T4), four typo kinds, delayed detection, word-boundary limit, correction, uncorrected rate (T5), dry-run transcript/summary/verbose (T6), pynput injector + AX check + frontmost app (T7), runner pause/abort/focus guard (T8), hotkeys (T9), CLI flags, exit codes 1/2/130, countdown, README with permissions (T10). Out-of-scope items are not planned. No gaps.

**Placeholder scan:** none.

**Type consistency:** `Event(key, delay_ms, hold_ms, note)` used identically in T1, T4–T8; `Controls`/`RunResult` in T8–T10; `PynputInjector(keyboard, special, sleep)` in T7 and constructed with no args in T10; `HotkeyListener(controls, pause_key, abort_key, log)` in T9 and T10; `accessibility_trusted`/`frontmost_app_name` names match T7 and T10.
