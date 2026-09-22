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


def test_keyboard_interrupt_is_a_clean_abort():
    inj = RecordingInjector()
    calls = {"n": 0}

    def sleep(_):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt

    result = run(EVENTS, inj, Controls(), sleep=sleep)
    assert result == RunResult(pressed=1, aborted=True)
    assert [k for k, _ in inj.pressed] == ["a"]
