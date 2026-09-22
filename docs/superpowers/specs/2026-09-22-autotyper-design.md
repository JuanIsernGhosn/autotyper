# autotyper: simulated human typing in Chrome (design)

Date: 2026-09-22

## Goal

A macOS command-line tool that types a given text into any Chrome input
(including ones that block pasting) the way a person would: variable speed,
context-dependent pauses, typing mistakes and their corrections. It is used
while the screen showing Chrome is being recorded; the terminal that drives the
tool lives on another, unrecorded screen.

## Decisions

- Keystrokes are injected at the operating-system level with `pynput`. They
  reach Chrome as if they came from a physical keyboard (`isTrusted` is true)
  and no page can tell them apart from real typing.
- macOS only. Requires the Accessibility permission (to inject) and the Input
  Monitoring permission (for the global hotkeys) on the app that runs Python
  (Terminal, iTerm, etc.).
- Python 3.12+, managed with `uv`. Runtime dependencies: `pynput`, `pyyaml`,
  `pyobjc-framework-Cocoa` and `pyobjc-framework-ApplicationServices`
  (frontmost-app detection and the Accessibility check).
- Spanish ISO keyboard layout by default for the neighbor-key table, `us` as
  the alternative.
- Controlled from the terminal with global hotkeys; no GUI.
- Defaults: 6 characters per second, 2 % typos, all of them corrected.

## Architecture

Two layers separated by a plain data interface:

1. **Planner** (`model.py`): a pure function `plan(text, config, rng) ->
   list[Event]`. Turns the text into a sequence of timed key events. Touches
   nothing on the system. Deterministic for a given seed.
2. **Runner** (`runner.py`): walks the events, waits the delays and delegates
   each press to an `Injector`. Handles pause, abort and the focus guard.

Modules of the `autotyper/` package:

| Module | Responsibility |
|---|---|
| `events.py` | Dataclass `Event(key, delay_ms, hold_ms, note)`. `key` is a character or one of `"backspace"`, `"enter"`, `"tab"`. `delay_ms` is the wait before pressing. `note` is optional text for the dry-run view (e.g. `"error:neighbor"`, `"fix"`). |
| `config.py` | Dataclass `TypingConfig` with every parameter and its default. Loads from YAML; CLI flags override. |
| `layouts.py` | Neighbor-key tables `es` and `us` (`dict[str, list[str]]`, lowercase). `neighbor(ch, layout, rng)` preserves case. |
| `model.py` | Planner: rhythm, drift, contextual pauses, typos and corrections. |
| `injector.py` | Protocol `Injector.press(key: str, hold_s: float)`. Implementations `PynputInjector` (real) and `RecordingInjector` (tests). |
| `focus.py` | `frontmost_app_name() -> str | None` through `NSWorkspace`, and `accessibility_trusted(prompt)` through `AXIsProcessTrustedWithOptions`. Both return `None` outside macOS or when the import fails. |
| `runner.py` | `run(events, injector, controls, ...)` with pause, abort and focus guard. `Controls` holds the `paused` / `aborted` flags the hotkeys update. |
| `hotkeys.py` | Global `pynput` listener that updates `Controls`. Default keys: F8 pause/resume, Esc abort. |
| `dryrun.py` | Renders the event list as a readable transcript plus statistics. |
| `cli.py` | The `autotyper` entry point. |

## Typing model

All times are milliseconds. `rng` is a `random.Random(seed)`.

### Base rhythm

- `base = 1000 / cps`.
- Interval for each key: `base * drift * ctx * lognormal(mu=0, sigma=0.35)`.
- **Drift**: a mean-reverting process updated on every key:
  `drift += 0.02 * (1 - drift) + gauss(0, 0.05)`, clamped to `[0.6, 1.6]`.
  Simulates bursts and fatigue over tens of seconds.
- **Context multiplier** (`ctx`): uppercase 1.4, digit 1.3, punctuation or
  symbol 1.3, the 3 keys after a correction 1.2, everything else 1.0.

### Pauses added before the next key

- After `,` `;` `:`: uniform 150–400.
- After `.` `!` `?` `…`: uniform 300–900.
- After a line break: uniform 500–1500.
- At the start of a word (after a space), with probability
  `think_pause_rate` (default 0.03): uniform 800–2500.

### Key hold time

`hold_ms = gauss(60, 15)` clamped to `[25, 120]`. Backspace bursts use the same
model.

### Typos

Only letters (`str.isalpha()`) get typos. With probability `error_rate` per
character a kind is chosen by weight:

| Kind | Weight | Typed | Intended | Advance |
|---|---|---|---|---|
| `neighbor` | 0.50 | adjacent key | `c` | 1 |
| `transpose` | 0.20 | `c2 c1` | `c1 c2` | 2 (only if `c2` is a letter) |
| `double` | 0.15 | `c c` | `c` | 1 |
| `omit` | 0.15 | nothing | `c` | 1 |

Detection: `k` further correct characters are typed before the mistake is
noticed, with `k = 0` with probability 0.5 and `k ∈ {1, 2, 3}` uniform
otherwise, never past the end of the current word (no space or line break is
crossed). For `omit`, `k` is at least 1; if there is no room the kind becomes
`double`. Because an omission types no wrong key, its `error:omit` note goes on
the first key typed after it.

Correction, with probability `1 - uncorrected_rate` (default 1.0):

1. Reaction pause: uniform 200–500.
2. `len(typed) + k` backspaces, uniform 80–140 apart.
3. The correct sequence plus the `k` extra characters are retyped with `ctx`
   1.2.

If not corrected, the mistake stays in the final text.

Invariant: with `uncorrected_rate = 0`, replaying the events onto a buffer
(applying characters and backspaces) yields exactly the original text.

### Special characters

- `\n` is emitted as `enter`, `\t` as `tab`. `\r` is dropped.
- Any other character is emitted as is; `pynput` injects it as a Unicode
  string, which covers `ñ`, accents and symbols not on the layout.

## Runner and safety

Command flow:

1. Load the text (file or `-` for stdin) and the configuration.
2. Plan the events.
3. Start the hotkey listener.
4. Count down `countdown` seconds (default 5), printing each second; the user
   clicks the Chrome input meanwhile.
5. For each event: check `aborted` (stop), wait while `paused`, check the
   focus guard, sleep `delay_ms`, press with `hold_ms`.
6. On completion or abort, stop the listener and print a summary.

Focus guard: if `frontmost_app_name()` differs from `app_name` (default
`"Google Chrome"`), the runner auto-pauses and says so on the terminal; it
resumes only when Chrome is back in front. It can be disabled with
`--no-focus-guard`. Where detection returns `None` the guard is ignored.

While paused (manually or automatically) time does not count; on resume the
pending event's `delay_ms` is honoured.

## Configuration

`TypingConfig` (same names in YAML and CLI):

| Field | Default |
|---|---|
| `cps` | 6.0 |
| `speed_sigma` | 0.35 |
| `error_rate` | 0.02 |
| `uncorrected_rate` | 0.0 |
| `think_pause_rate` | 0.03 |
| `layout` | `es` |
| `app_name` | `Google Chrome` |
| `focus_guard` | true |
| `countdown` | 5 |
| `seed` | null (random) |
| `pause_key` | `f8` |
| `abort_key` | `esc` |

## CLI

```
autotyper TEXT.txt [--cps 6] [--error-rate 0.02] [--layout es] [--seed 42]
                   [--countdown 5] [--profile profile.yaml] [--app "Google Chrome"]
                   [--no-focus-guard] [--dry-run] [--verbose]
cat TEXT.txt | autotyper -
```

`--dry-run` injects nothing: it prints the transcript as it would be typed
(backspaces as `⌫`) and a summary with estimated duration, number of typos and
effective cps. `--verbose` adds one line per event with delay and hold time.

## Error handling

- No Accessibility permission: the CLI calls the prompting variant of the
  check so macOS shows its dialog, then explains what to enable and exits with
  code 2.
- Missing file, empty text, invalid configuration or invalid YAML: a one-line
  message and code 1.
- Ctrl+C during the countdown: nothing typed, code 130. Ctrl+C or Esc during
  typing: a summary of how many keys were pressed, code 130.
- Any failure inside the injector: a one-line message, code 1, never a
  traceback.

## Tests

- `model`: with a fixed seed, replaying the events onto a buffer returns the
  original text; with `error_rate = 0` there are no backspaces; with
  `error_rate = 1` on a text of letters there are backspaces and error notes;
  effective cps of a long text with `error_rate = 0` is between 0.6 and 1.6
  times `cps`; emitted neighbor keys belong to the layout table; `\n` yields
  `enter`.
- `layouts`: every key in the table has at least one neighbor and the
  neighbors exist in the table.
- `runner`: with `RecordingInjector` and a fake clock, every key is pressed in
  order, delays are honoured, `aborted` cuts the run, `paused` holds without
  losing events, the focus guard pauses when the front app does not match,
  and a `KeyboardInterrupt` is a clean abort.
- `dryrun`: the transcript of a plan without typos is the original text.
- `config`: YAML and flags combine with the right precedence.
- `cli`: dry run, stdin, profiles, exit codes, and the real path with fake
  injector and hotkeys.

No integration tests against Chrome; manual verification is done with
`--dry-run` and then with a real input.

## Out of scope

- Mouse movement, clicks, or locating the input automatically.
- Linux and Windows.
- A GUI or menu-bar app.
- Typing without focus (through the Chrome DevTools Protocol).
