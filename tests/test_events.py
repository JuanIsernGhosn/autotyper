from autotyper.events import BACKSPACE, ENTER, TAB, Event, replay


def test_replay_types_characters_in_order():
    events = [Event("h", 0, 50), Event("i", 0, 50)]
    assert replay(events) == "hi"


def test_replay_backspace_removes_last_char():
    events = [Event("h", 0, 50), Event("x", 0, 50), Event(BACKSPACE, 0, 50), Event("i", 0, 50)]
    assert replay(events) == "hi"


def test_replay_backspace_on_empty_buffer_is_noop():
    assert replay([Event(BACKSPACE, 0, 50), Event("a", 0, 50)]) == "a"


def test_replay_enter_and_tab_map_to_whitespace():
    events = [Event("a", 0, 50), Event(ENTER, 0, 50), Event(TAB, 0, 50), Event("b", 0, 50)]
    assert replay(events) == "a\n\tb"


def test_event_default_note_is_empty():
    assert Event("a", 1.0, 2.0).note == ""
