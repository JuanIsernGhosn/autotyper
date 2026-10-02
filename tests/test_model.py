import random

from autotyper.config import TypingConfig
from autotyper.events import BACKSPACE, ENTER, TAB, replay
from autotyper.model import plan


def cfg(**kw):
    base = {"error_rate": 0.0, "think_pause_rate": 0.0}
    base.update(kw)
    return TypingConfig(**base)


def test_plan_without_errors_reproduces_text():
    text = "Hola, mundo. ¿Qué tal?\nBien."
    events = plan(text, cfg(), random.Random(1))
    assert replay(events) == text
    assert all(e.key != BACKSPACE for e in events)


def test_plan_is_deterministic_for_a_seed():
    a = plan("hola mundo", cfg(), random.Random(3))
    b = plan("hola mundo", cfg(), random.Random(3))
    assert a == b


def test_newline_and_tab_become_special_keys_and_cr_is_dropped():
    events = plan("a\r\n\tb", cfg(), random.Random(1))
    assert [e.key for e in events] == ["a", ENTER, TAB, "b"]


def test_effective_cps_is_near_configured():
    text = "lorem ipsum dolor sit amet " * 40
    events = plan(text, cfg(cps=6.0), random.Random(5))
    seconds = sum(e.delay_ms for e in events) / 1000
    effective = len(text) / seconds
    assert 0.6 * 6.0 <= effective <= 1.6 * 6.0


def test_hold_is_within_bounds_and_delays_are_positive():
    events = plan("abc def", cfg(), random.Random(2))
    for e in events:
        assert 25 <= e.hold_ms <= 120
        assert e.delay_ms > 0


def test_pause_after_sentence_end_is_longer_than_after_letter():
    rng = random.Random(9)
    events = plan("a. b", cfg(), rng)
    # events: a . space b -> the space carries the post-period pause
    assert events[2].delay_ms >= 300


def test_pause_after_newline_is_longest():
    events = plan("a\nb", cfg(), random.Random(9))
    assert events[2].delay_ms >= 500


def test_think_pause_can_happen_at_word_start():
    events = plan("uno dos tres", cfg(think_pause_rate=1.0), random.Random(1))
    # "dos" starts at index 4, "tres" at index 8
    assert events[4].delay_ms >= 800
    assert events[8].delay_ms >= 800


from autotyper.layouts import LAYOUTS


def test_plan_with_errors_still_reproduces_text_when_all_corrected():
    text = "Ayer fui al mercado y compré manzanas, peras y ñoras.\nLuego volví a casa."
    for seed in range(30):
        events = plan(text, cfg(error_rate=0.3), random.Random(seed))
        assert replay(events) == text, f"seed {seed}"


def test_high_error_rate_produces_backspaces_and_error_notes():
    events = plan("abcdefghij klmnopqrst", cfg(error_rate=1.0), random.Random(1))
    assert any(e.key == BACKSPACE for e in events)
    kinds = {e.note for e in events if e.note.startswith("error:")}
    assert kinds <= {"error:neighbor", "error:transpose", "error:double", "error:omit"}
    assert kinds


def test_all_four_error_kinds_show_up_over_many_seeds():
    seen = set()
    for seed in range(40):
        events = plan("hola mundo cruel", cfg(error_rate=1.0), random.Random(seed))
        seen |= {e.note for e in events if e.note.startswith("error:")}
    assert seen == {"error:neighbor", "error:transpose", "error:double", "error:omit"}


def test_neighbor_errors_come_from_layout_table():
    text = "sdfg" * 20
    events = plan(text, cfg(error_rate=1.0), random.Random(4))
    wrong = [e for e in events if e.note == "error:neighbor"]
    assert wrong
    for e in wrong:
        # the intended letter is unknown here, so check the wrong key is a
        # neighbor of at least one of the letters in the text
        assert any(e.key.lower() in LAYOUTS["es"][c] for c in "sdfg")


def test_uncorrected_errors_change_final_text():
    text = "abcdefghijklmnopqrstuvwxyz" * 3
    events = plan(text, cfg(error_rate=1.0, uncorrected_rate=1.0), random.Random(2))
    assert replay(events) != text
    assert all(e.key != BACKSPACE for e in events)


def test_correction_does_not_cross_word_boundary():
    # With k up to 3 extra chars, a typo on "ab" can only ever backspace the
    # current word, never the space before it.
    for seed in range(30):
        events = plan("xy ab cd", cfg(error_rate=1.0), random.Random(seed))
        assert replay(events) == "xy ab cd"
        typed = ""
        for e in events:
            if e.key == BACKSPACE:
                assert typed[-1] != " ", "backspaced over a space"
                typed = typed[:-1]
            else:
                typed += e.key


def test_correction_has_reaction_pause_before_first_backspace():
    events = plan("abcdef", cfg(error_rate=1.0), random.Random(1))
    first_bs = next(e for e in events if e.key == BACKSPACE)
    assert first_bs.delay_ms >= 200


def test_accented_letters_never_use_neighbor_kind():
    events = plan("ááááá ééééé", cfg(error_rate=1.0), random.Random(1))
    assert not any(e.note == "error:neighbor" for e in events)
    assert replay(events) == "ááááá ééééé"


from autotyper.model import protected_mask


def test_protected_mask_covers_urls_emails_numbers_and_code():
    text = "ve a https://ejemplo.com/x?a=1 o escribe a juan@mail.com, usa `git push` y el 2024-09-29"
    mask = protected_mask(text)
    assert all(mask[i] for i in range(text.index("https"), text.index("?a=1") + 4))
    assert all(mask[i] for i in range(text.index("juan@"), text.index(".com,") + 4))
    assert all(mask[i] for i in range(text.index("`git"), text.index("push`") + 5))
    assert all(mask[i] for i in range(text.index("2024"), len(text)))
    assert not mask[text.index("ve")]
    assert not mask[text.index("usa")]


def test_no_typos_inside_a_protected_url():
    text = "https://ejemplo.com/pagina/larga"
    for seed in range(10):
        events = plan(text, cfg(error_rate=1.0), random.Random(seed))
        assert not any(e.note.startswith("error:") for e in events), seed


def test_typos_still_happen_outside_protected_spans():
    events = plan("mira https://ejemplo.com/pagina ahora", cfg(error_rate=1.0), random.Random(1))
    assert any(e.note.startswith("error:") for e in events)
    assert replay(events) == "mira https://ejemplo.com/pagina ahora"


def test_protect_spans_can_be_disabled():
    text = "https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.com"
    events = plan(text, cfg(error_rate=1.0, protect_spans=False), random.Random(1))
    assert any(e.note.startswith("error:") for e in events)
