"""Turn text into human-looking timed keystrokes."""

from __future__ import annotations

import math
import random
import re
import unicodedata

from autotyper.config import TypingConfig
from autotyper.events import BACKSPACE, ENTER, TAB, WORD_BACKSPACE, Event
from autotyper.layouts import neighbor

_PROTECTED = re.compile(
    r"https?://\S+"  # URLs
    r"|www\.\S+"
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"  # emails
    r"|`[^`\n]*`"  # inline code
    r"|\d[\d.,:/-]*\d"  # numbers, dates, times
)

_ACCENTED = frozenset("áéíóúüÁÉÍÓÚÜ")

_PUNCT_SHORT = frozenset(",;:")
_PUNCT_LONG = frozenset(".!?…")

_CTX_UPPER = 1.4
_CTX_DIGIT = 1.3
_CTX_SYMBOL = 1.3
_CTX_AFTER_FIX = 1.2
_SLOW_KEYS_AFTER_FIX = 3


def _strip_accent(ch: str) -> str:
    return unicodedata.normalize("NFD", ch)[0]


def protected_mask(text: str) -> list[bool]:
    """True at every index where a typo must not be introduced."""
    mask = [False] * len(text)
    for m in _PROTECTED.finditer(text):
        for i in range(m.start(), m.end()):
            mask[i] = True
    return mask


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
        self._mask = protected_mask(text) if self.cfg.protect_spans else [False] * len(text)
        i = 0
        at_word_start = True
        self._word_start = 0
        while i < len(text):
            ch = text[i]
            if at_word_start and not ch.isspace():
                self._word_start = i
                if self.rng.random() < self.cfg.think_pause_rate:
                    self.pending_pause_ms += self.rng.uniform(800, 2500)
            if ch.isalpha() and not self._mask[i] and self.rng.random() < self.cfg.error_rate:
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

    # -- typos ------------------------------------------------------------

    _ERROR_KINDS = ("neighbor", "transpose", "double", "omit")
    _ERROR_WEIGHTS = (0.50, 0.20, 0.15, 0.15)

    def _typo(self, text: str, i: int) -> int:
        """Emit a mistyped chunk starting at text[i], maybe fix it, return next index."""
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in _ACCENTED and self.rng.random() < 0.7:
            kind = "accent"
        elif ch.isupper() and ch.lower() != ch and self.rng.random() < 0.3:
            kind = "case"
        else:
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
        elif kind == "accent":
            wrong, correct, advance = [_strip_accent(ch)], [ch], 1
        elif kind == "case":
            wrong, correct, advance = [ch.lower()], [ch], 1
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
        while len(extra) < k and j < len(text) and not text[j].isspace() and not self._mask[j]:
            extra.append(text[j])
            j += 1
        if kind == "omit" and not extra:
            kind, wrong = "double", [ch, ch]

        for w in wrong:
            self._emit_char(w, note=f"error:{kind}")
        for n, x in enumerate(extra):
            # An omission types nothing wrong, so tag the key typed right after it.
            self._emit_char(x, note="error:omit" if kind == "omit" and n == 0 else "")

        if self.rng.random() < self.cfg.uncorrected_rate:
            return j

        word_so_far = text[self._word_start : j]
        if len(extra) >= 2 and word_so_far.isalpha() and self.rng.random() < self.cfg.word_delete_rate:
            # Noticed late: wipe the whole word with Option+Backspace and retype it.
            self.pending_pause_ms = self.rng.uniform(250, 600)
            delay = self.rng.uniform(150, 300) + self._take_pending()
            self.events.append(Event(WORD_BACKSPACE, delay, self._hold_ms(), "fix"))
            self.slow_after_fix = _SLOW_KEYS_AFTER_FIX
            for c in word_so_far:
                self._emit_char(c, note="fix")
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


def plan(text: str, config: TypingConfig, rng: random.Random) -> list[Event]:
    return Planner(config, rng).plan(text)
