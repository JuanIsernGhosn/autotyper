# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
