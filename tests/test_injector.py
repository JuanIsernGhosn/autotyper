from autotyper.injector import PynputInjector, RecordingInjector


def test_recording_injector_stores_presses():
    inj = RecordingInjector()
    inj.press("a", 0.05)
    inj.press("backspace", 0.06)
    assert inj.pressed == [("a", 0.05), ("backspace", 0.06)]


class FakeKeyboard:
    def __init__(self):
        self.log = []

    def press(self, k):
        self.log.append(("down", k))

    def release(self, k):
        self.log.append(("up", k))


def test_pynput_injector_maps_special_keys_and_holds():
    kb = FakeKeyboard()
    sleeps = []
    inj = PynputInjector(keyboard=kb, special={"backspace": "BS"}, sleep=sleeps.append)
    inj.press("backspace", 0.04)
    inj.press("ñ", 0.05)
    assert kb.log == [("down", "BS"), ("up", "BS"), ("down", "ñ"), ("up", "ñ")]
    assert sleeps == [0.04, 0.05]


def test_accessibility_trusted_passes_prompt_option(monkeypatch):
    import sys
    import types

    from autotyper import focus

    seen = {}
    fake = types.ModuleType("ApplicationServices")
    fake.kAXTrustedCheckOptionPrompt = "AXTrustedCheckOptionPrompt"
    fake.AXIsProcessTrustedWithOptions = lambda opts: seen.setdefault("opts", opts) and True
    monkeypatch.setitem(sys.modules, "ApplicationServices", fake)
    assert focus.accessibility_trusted(prompt=True) is True
    assert seen["opts"] == {"AXTrustedCheckOptionPrompt": True}


def test_terminal_injector_writes_keys_and_erases_on_backspace():
    import io

    from autotyper.injector import TerminalInjector

    out = io.StringIO()
    inj = TerminalInjector(out)
    for k in ("a", "b", "backspace", "enter", "tab", "c"):
        inj.press(k, 0)
    assert out.getvalue() == "ab\b \b\n\tc"
    assert inj.buffer == "a\n\tc"


def test_pynput_injector_sends_option_backspace_chord():
    kb = FakeKeyboard()
    inj = PynputInjector(keyboard=kb, special={"backspace": "BS", "alt": "ALT"}, sleep=lambda _: None)
    inj.press("word_backspace", 0.05)
    assert kb.log == [("down", "ALT"), ("down", "BS"), ("up", "BS"), ("up", "ALT")]


def test_terminal_injector_erases_word():
    import io

    from autotyper.injector import TerminalInjector

    out = io.StringIO()
    inj = TerminalInjector(out)
    for k in "ab cd":
        inj.press(k, 0)
    inj.press("word_backspace", 0)
    assert out.getvalue() == "ab cd" + "\b \b" * 2
    assert inj.buffer == "ab "


def test_input_monitoring_granted_maps_iokit_codes(monkeypatch):
    from autotyper import focus

    class FakeIOKit:
        def __init__(self, code):
            self.IOHIDCheckAccess = lambda kind: code

    monkeypatch.setattr(focus, "_iokit", lambda: FakeIOKit(0))
    assert focus.input_monitoring_granted() is True
    monkeypatch.setattr(focus, "_iokit", lambda: FakeIOKit(1))
    assert focus.input_monitoring_granted() is False
    monkeypatch.setattr(focus, "_iokit", lambda: FakeIOKit(2))
    assert focus.input_monitoring_granted() is None
    monkeypatch.setattr(focus, "_iokit", lambda: None)
    assert focus.input_monitoring_granted() is None
