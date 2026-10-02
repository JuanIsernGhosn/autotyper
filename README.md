# autotyper

Type any text into the focused input as if a person were typing it: variable speed, pauses after punctuation, realistic typos and their corrections. Keystrokes are injected at the operating-system level, so they work in inputs that block pasting and are indistinguishable from a real keyboard to the page.

Built for screen recordings and demos where pasting a block of text would look fake.

![autotyper typing a short text with a couple of corrected typos](docs/demo.gif)

macOS only.

## How it works

```
text file ──▶ planner ──▶ timed keystrokes ──▶ runner ──▶ macOS keyboard events ──▶ Chrome (or any app)
                 │                                 │
        rhythm, pauses, typos            pause / abort hotkeys,
        and corrections                  auto-pause when the target app loses focus
```

1. The planner turns your text into a list of keystrokes with individual delays and hold times. It is deterministic for a given seed, so a run can be previewed and repeated.
2. The runner waits for a countdown, then replays the keystrokes through the system keyboard, watching for your hotkeys and for the target app losing focus.

Here is what a preview looks like with a deliberately high error rate. `⌫` is a backspace and `⏎` is Enter:

```
Holl⌫⌫la, u⌫mundo. Ez⌫sto es una prieb⌫⌫⌫ueba con ñ y tildes: canx⌫ciónn.⌫⌫⌫n.⏎
Seug⌫⌫guna⌫da línsa.⌫⌫⌫ea.⏎
```

## Features

- **Human rhythm.** Per-key intervals follow a log-normal distribution around your chosen speed, with a slow drift that produces fast bursts and tired stretches.
- **Context-aware pauses.** Capitals, digits and symbols are slower. Commas, sentence ends and new paragraphs add pauses. Occasional longer "thinking" pauses at the start of a word.
- **Realistic typos.** Adjacent-key hits, transposed letters, doubled letters, skipped letters, missing accents and lost capitals, using the Spanish or US keyboard layout. Mistakes are noticed immediately or a few characters later, then fixed with a burst of backspaces, or by wiping the whole word, and a slightly slower retype. URLs, emails, numbers and code spans are typed carefully, with no typos.
- **Fits your recording.** Set the speed in characters or words per minute, or give a target duration and let it work out the speed.
- **Real key events.** Each key is held for a realistic time, and everything goes through the OS, so `isTrusted` is `true` and paste-blocking inputs accept it.
- **Safe to run while recording.** Countdown or start-on-key, live progress in the terminal, global pause and abort hotkeys, automatic pause whenever the target app or window is not in front, and a resume hint if you abort.
- **Dry run.** Preview the exact keystroke sequence, duration and effective speed without touching the keyboard, or replay it live in the terminal to feel the rhythm.
- **Profiles.** Keep your favourite settings in a YAML file; command-line flags override it.

## Installation

### With Homebrew

```sh
brew install JuanIsernGhosn/tap/autotyper
```

Later updates come with `brew upgrade`.

### With uv

Requires [uv](https://docs.astral.sh/uv/). Python is downloaded automatically if needed.

```sh
uv tool install git+https://github.com/JuanIsernGhosn/autotyper
```

Or use the installer, which sets up uv first if it is missing:

```sh
curl -fsSL https://raw.githubusercontent.com/JuanIsernGhosn/autotyper/main/install.sh | sh
```

To try it once without installing:

```sh
uvx --from git+https://github.com/JuanIsernGhosn/autotyper autotyper --help
```

### From source

```sh
git clone https://github.com/JuanIsernGhosn/autotyper.git
cd autotyper
uv sync
uv run autotyper --help
```

## Permissions

macOS must allow your terminal app to control the keyboard. On the first real run autotyper asks the system to show its permission dialog, which adds the app to the list for you.

In System Settings > Privacy & Security:

- **Accessibility**: enable your terminal app (Terminal, iTerm2, VS Code, ...). Without this no keys are injected.
- **Input Monitoring**: enable the same app. This is only needed for the global pause and abort hotkeys; autotyper warns when it is missing.

Reopen the terminal window after changing permissions.

## Usage

```sh
# preview, nothing is typed
autotyper text.txt --dry-run
autotyper text.txt --dry-run --verbose
autotyper text.txt --dry-run --live        # replays the rhythm in the terminal

# type for real: you get a 5 second countdown to click the target input
autotyper text.txt
autotyper text.txt --wpm 50 --error-rate 0.03 --seed 42
autotyper text.txt --duration 45           # fit the whole text into 45 seconds
autotyper text.txt --wait-for-key          # start when you press F8 in the input
cat text.txt | autotyper -

# use a profile; flags on the command line win
autotyper text.txt --profile profile.yaml
```

### While typing

| Key | Action |
|---|---|
| **F8** | pause / resume |
| **Esc** | abort |
| **Ctrl+C** in the terminal | abort |

Both hotkeys are global, so you never have to switch back to the terminal. The terminal shows a progress line with the keys typed and the time left.

If the target app leaves the foreground, typing pauses by itself and resumes when the app is back. The target is Google Chrome by default; change it with `--app "Safari"`, require a window title with `--window "My form"`, or disable the guard with `--no-focus-guard`.

Keep the terminal on a screen that is not being recorded.

### Resuming after an abort

When you abort, autotyper prints how many characters made it into the field and the exact `--start-at N` to continue from there. If the field ends in a typo that was not fixed yet, delete it by hand first.

### Options

| Flag | Default | Description |
|---|---|---|
| `--cps` | 6 | average characters per second |
| `--wpm` | | words per minute, instead of `--cps` (1 word = 5 characters) |
| `--duration` | | seconds the whole text should take; overrides the speed |
| `--speed-sigma` | 0.35 | spread of the interval between keys |
| `--error-rate` | 0.02 | probability of a typo per letter |
| `--uncorrected-rate` | 0 | share of typos left unfixed |
| `--word-delete-rate` | 0.3 | chance of wiping the whole word after a late-noticed typo |
| `--think-pause-rate` | 0.03 | probability of a long pause at the start of a word |
| `--layout` | es | keyboard layout for adjacent-key typos: `es` or `us` |
| `--no-protect-spans` | off | allow typos inside URLs, emails, numbers and code spans |
| `--app` | Google Chrome | app that must be in front for typing to proceed |
| `--window` | | text the front window title must contain |
| `--no-focus-guard` | off | never auto-pause on focus loss |
| `--countdown` | 5 | seconds to wait before typing starts |
| `--wait-for-key` | off | start on the pause key instead of a countdown |
| `--start-at` | 0 | skip the first N characters, to resume after an abort |
| `--seed` | random | seed for a reproducible run; printed on every run |
| `--pause-key` / `--abort-key` | f8 / esc | global hotkeys |
| `--dry-run` | off | print the keystroke plan and exit |
| `--verbose` | off | with `--dry-run`, list every keystroke with its timing |
| `--live` | off | with `--dry-run`, replay the rhythm in the terminal in real time |
| `--no-default-profile` | off | ignore the default profile |

### Profiles

```yaml
# profile.yaml
cps: 7
error_rate: 0.025
uncorrected_rate: 0.1
think_pause_rate: 0.04
layout: es
```

Any option above can be set in the profile using its flag name with underscores instead of dashes. A profile at `~/.config/autotyper/config.yaml` is loaded automatically; `--profile` and flags override it.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | finished |
| 1 | bad input, bad configuration or a typing failure |
| 2 | the terminal app is not allowed to control the keyboard |
| 130 | aborted with Esc or Ctrl+C |

## Requirements

- macOS 13 or later
- [uv](https://docs.astral.sh/uv/) to install, Python 3.12 or later is fetched automatically
- Accessibility permission for your terminal app

Only use it on forms and sites where you are allowed to automate input.

## Development

```sh
uv sync
uv run pytest
./scripts/record-demo.sh   # re-record docs/demo.gif (needs asciinema and agg)
```

The planner is pure and seeded, so all typing behaviour is covered by unit tests without touching the keyboard.

## Author

Juan Isern · [@JuanIsernGhosn](https://github.com/JuanIsernGhosn)

## License

[MIT](LICENSE)
