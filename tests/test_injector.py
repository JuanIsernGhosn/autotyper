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
