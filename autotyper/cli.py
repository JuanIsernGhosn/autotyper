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
    p.add_argument("--layout", help="keyboard layout for neighbor typos: es or us (default es)")
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
