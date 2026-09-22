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
