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
