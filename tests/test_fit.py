from autotyper.config import TypingConfig
from autotyper.fit import fit_duration


def test_fit_duration_lands_within_ten_percent():
    text = ("Hola, esto es una frase de prueba. " * 12).strip()
    events, cps = fit_duration(text, TypingConfig(), seed=3, target_s=40)
    total = sum(e.delay_ms for e in events) / 1000
    assert abs(total - 40) / 40 < 0.10
    assert 0.5 <= cps <= 40


def test_fit_duration_is_deterministic():
    a = fit_duration("hola mundo " * 20, TypingConfig(), 1, 20)
    b = fit_duration("hola mundo " * 20, TypingConfig(), 1, 20)
    assert a == b
