# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-10-02

### Added

- `--wpm` as an alternative to `--cps`, and `--duration` to fit the whole text
  into a target number of seconds.
- Live progress line in the terminal while typing.
- `--wait-for-key` to start typing on the pause key instead of a countdown.
- `--start-at` and a resume hint after an abort.
- `--dry-run --live` replays the keystroke rhythm in the terminal.
- Typos are never introduced inside URLs, emails, numbers and inline code
  (`--no-protect-spans` to disable).
- Missing-accent and lost-capital typos; whole-word deletion with
  Option+Backspace after a late-noticed typo (`--word-delete-rate`).
- Warning, with the system prompt, when Input Monitoring is missing.
- Default profile at `~/.config/autotyper/config.yaml`
  (`--no-default-profile` to skip it).
- `--window` to also require the front window title to contain a text.
- Demo recording in the README.

## [0.1.0] - 2026-09-22

### Added

- Human-like typing planner: log-normal key intervals, slow speed drift,
  context-aware pauses after punctuation and paragraphs, thinking pauses.
- Typos with delayed corrections: adjacent key, transposition, doubled and
  skipped letters, on Spanish and US layouts. Optional uncorrected typos.
- OS-level keystroke injection through pynput with realistic key hold times.
- Countdown, global pause (F8) and abort (Esc) hotkeys, clean Ctrl+C handling.
- Automatic pause when the target app (Google Chrome by default) loses focus.
- `--dry-run` preview with transcript, timing summary and per-key listing.
- YAML profiles with command-line overrides.
- macOS Accessibility permission check that triggers the system prompt.
