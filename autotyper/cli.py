"""Command-line entry point."""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import yaml

from autotyper import __version__
from autotyper.config import TypingConfig, default_profile_path, load_profile, merge
from autotyper.dryrun import summary, transcript, verbose_lines
from autotyper.events import replay
from autotyper.fit import fit_duration
from autotyper.focus import (
    accessibility_trusted,
    frontmost_app_name,
    input_monitoring_granted,
    request_input_monitoring,
)
from autotyper.hotkeys import HotkeyListener
from autotyper.injector import PynputInjector, TerminalInjector
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
    p.add_argument("--no-default-profile", action="store_true", dest="no_default_profile", help="ignore ~/.config/autotyper/config.yaml")
    p.add_argument("--cps", type=float, help="characters per second (default 6)")
    p.add_argument("--wpm", type=float, help="words per minute, alternative to --cps (1 word = 5 chars)")
    p.add_argument("--duration", type=float, help="fit the whole text into this many seconds (overrides speed)")
    p.add_argument("--speed-sigma", type=float, dest="speed_sigma", help="per-key jitter (default 0.35)")
    p.add_argument("--error-rate", type=float, dest="error_rate", help="typo probability per letter (default 0.02)")
    p.add_argument("--uncorrected-rate", type=float, dest="uncorrected_rate", help="share of typos left unfixed (default 0)")
    p.add_argument("--think-pause-rate", type=float, dest="think_pause_rate", help="long pause probability per word (default 0.03)")
    p.add_argument("--word-delete-rate", type=float, dest="word_delete_rate", help="chance of deleting the whole word after a late-noticed typo (default 0.3)")
    p.add_argument("--layout", help="keyboard layout for neighbor typos: es or us (default es)")
    p.add_argument("--no-protect-spans", action="store_true", dest="no_protect_spans", help="allow typos inside URLs, emails, numbers and code spans")
    p.add_argument("--app", dest="app_name", help='app that must be in front (default "Google Chrome")')
    p.add_argument("--no-focus-guard", action="store_true", help="do not auto-pause when the app loses focus")
    p.add_argument("--countdown", type=int, help="seconds to wait before typing (default 5)")
    p.add_argument("--wait-for-key", action="store_true", dest="wait_for_key", help="instead of a countdown, start when the pause key is pressed")
    p.add_argument("--seed", type=int, help="random seed for reproducible runs")
    p.add_argument("--start-at", type=int, default=0, dest="start_at", help="skip the first N characters (resume after an abort)")
    p.add_argument("--pause-key", dest="pause_key", help="global pause/resume key (default f8)")
    p.add_argument("--abort-key", dest="abort_key", help="global abort key (default esc)")
    p.add_argument("--dry-run", action="store_true", help="print what would be typed, inject nothing")
    p.add_argument("--verbose", action="store_true", help="with --dry-run, list every keystroke")
    p.add_argument("--live", action="store_true", help="with --dry-run, replay the rhythm in the terminal in real time")
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
    default = default_profile_path()
    if not args.no_default_profile and default.is_file():
        cfg = merge(cfg, load_profile(default))
    if args.profile:
        cfg = merge(cfg, load_profile(args.profile))
    overrides = {
        "cps": args.cps,
        "wpm": args.wpm,
        "speed_sigma": args.speed_sigma,
        "error_rate": args.error_rate,
        "uncorrected_rate": args.uncorrected_rate,
        "think_pause_rate": args.think_pause_rate,
        "word_delete_rate": args.word_delete_rate,
        "layout": args.layout,
        "protect_spans": False if args.no_protect_spans else None,
        "app_name": args.app_name,
        "focus_guard": False if args.no_focus_guard else None,
        "countdown": args.countdown,
        "wait_for_key": True if args.wait_for_key else None,
        "seed": args.seed,
        "pause_key": args.pause_key,
        "abort_key": args.abort_key,
    }
    return merge(cfg, overrides)


def _progress(done: int, total: int, remaining_s: float) -> None:
    print(f"\r  {done}/{total} keys  ~{remaining_s:4.0f} s left ", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.live and not args.dry_run:
        print("error: --live requires --dry-run", file=sys.stderr)
        return EXIT_INPUT
    if args.duration is not None and (args.cps is not None or args.wpm is not None):
        print("error: --duration cannot be combined with --cps or --wpm", file=sys.stderr)
        return EXIT_INPUT
    try:
        text = _read_text(args.text)
        if args.start_at < 0:
            raise ValueError("--start-at must be >= 0")
        text = text[args.start_at :]
        if not text.strip():
            raise ValueError("text is empty")
        cfg = _build_config(args)
    except yaml.YAMLError as exc:
        print(f"error: invalid YAML in profile {args.profile}: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT

    seed = cfg.seed if cfg.seed is not None else random.randrange(2**32)
    if args.duration is not None:
        try:
            events, fitted = fit_duration(text, cfg, seed, args.duration)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_INPUT
        print(f"fitted cps: {fitted:.2f}")
    else:
        events = plan(text, cfg, random.Random(seed))

    if args.dry_run:
        if args.live:
            result = run(events, TerminalInjector(), Controls(), sleep=time.sleep)
            print()
            if result.aborted:
                return EXIT_ABORTED
        else:
            print(transcript(events))
        print()
        if args.verbose:
            print("\n".join(verbose_lines(events)))
            print()
        print(summary(events))
        print(f"seed: {seed}")
        return EXIT_OK

    if accessibility_trusted(prompt=True) is False:
        print(
            "error: this process is not allowed to control the keyboard.\n"
            "macOS should have shown a dialog naming the app to allow. Enable it in\n"
            "System Settings > Privacy & Security > Accessibility (and Input Monitoring\n"
            "for the hotkeys), reopen the terminal window, then retry.\n"
            f"If the list shows no terminal app, add this binary: {sys.executable}",
            file=sys.stderr,
        )
        return EXIT_PERMISSION

    if input_monitoring_granted() is False:
        request_input_monitoring()
        print(
            "warning: Input Monitoring is not granted, so the pause/abort hotkeys will not work.\n"
            "Enable it in System Settings > Privacy & Security > Input Monitoring for your terminal app.",
            file=sys.stderr,
        )

    controls = Controls()
    hotkeys = HotkeyListener(controls, cfg.pause_key, cfg.abort_key)
    hotkeys.start()
    try:
        print(f"seed: {seed}   pause: {cfg.pause_key}   abort: {cfg.abort_key}")
        try:
            if cfg.wait_for_key:
                print(f"press {cfg.pause_key} in the target input to start ({cfg.abort_key} cancels)", flush=True)
                while not controls.started and not controls.aborted:
                    time.sleep(0.05)
                if controls.aborted:
                    print("cancelled before typing")
                    return EXIT_ABORTED
            else:
                for remaining in range(cfg.countdown, 0, -1):
                    print(f"typing in {remaining}... click the target input now", flush=True)
                    time.sleep(1)
                controls.started = True
        except KeyboardInterrupt:
            print("\naborted before typing, nothing typed")
            return EXIT_ABORTED
        try:
            result = run(
                events,
                PynputInjector(),
                controls,
                focus_check=frontmost_app_name if cfg.focus_guard else None,
                app_name=cfg.app_name,
                on_progress=_progress,
            )
            print()
        except Exception as exc:  # noqa: BLE001 - surface any injector/OS failure briefly
            print(f"error: typing failed ({type(exc).__name__}): {exc}", file=sys.stderr)
            return EXIT_INPUT
    finally:
        hotkeys.stop()

    if result.aborted:
        in_field = replay(events[: result.pressed])
        print(f"aborted after {result.pressed} keystrokes ({len(in_field)} characters in the field)")
        print(f"resume with --start-at {args.start_at + len(in_field)}")
        if not text.startswith(in_field):
            print("the field ends with an unfixed typo: delete it by hand before resuming")
        return EXIT_ABORTED
    print(f"done: {result.pressed} keystrokes")
    print(summary(events))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
