from types import SimpleNamespace

from autotyper.hotkeys import HotkeyListener, key_name
from autotyper.runner import Controls


def named(name):
    return SimpleNamespace(name=name)


def charkey(c):
    return SimpleNamespace(char=c)


def test_key_name_handles_named_and_char_keys():
    assert key_name(named("f8")) == "f8"
    assert key_name(charkey("a")) == "a"
    assert key_name(SimpleNamespace()) == ""
    assert key_name(SimpleNamespace(char=None)) == ""


def test_pause_key_toggles_and_abort_key_sets():
    controls = Controls()
    logs = []
    hk = HotkeyListener(controls, pause_key="f8", abort_key="esc", log=logs.append)
    hk.on_press(named("f8"))
    assert controls.paused is True
    hk.on_press(named("f8"))
    assert controls.paused is False
    hk.on_press(named("esc"))
    assert controls.aborted is True
    assert logs


def test_other_keys_are_ignored():
    controls = Controls()
    hk = HotkeyListener(controls, log=lambda _: None)
    hk.on_press(charkey("x"))
    assert controls == Controls()
