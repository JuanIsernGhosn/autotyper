import random

import pytest

from autotyper.layouts import LAYOUTS, neighbor


@pytest.mark.parametrize("layout", ["es", "us"])
def test_every_key_has_letter_neighbors_that_exist_in_table(layout):
    table = LAYOUTS[layout]
    assert table, "layout table must not be empty"
    for key, neighbors in table.items():
        assert neighbors, f"{key!r} has no neighbors"
        for n in neighbors:
            assert n.isalpha()
            assert n in table


def test_es_layout_knows_enie():
    assert "ñ" in LAYOUTS["es"]
    assert "l" in LAYOUTS["es"]["ñ"]


def test_us_layout_has_no_enie():
    assert "ñ" not in LAYOUTS["us"]


def test_neighbor_returns_adjacent_key():
    rng = random.Random(1)
    for _ in range(50):
        assert neighbor("s", "es", rng) in LAYOUTS["es"]["s"]


def test_neighbor_preserves_upper_case():
    rng = random.Random(1)
    n = neighbor("S", "es", rng)
    assert n.isupper()
    assert n.lower() in LAYOUTS["es"]["s"]


def test_neighbor_returns_none_for_unknown_char():
    assert neighbor("á", "es", random.Random(1)) is None
    assert neighbor("3", "es", random.Random(1)) is None
