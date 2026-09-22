import pytest

from autotyper.config import TypingConfig, load_profile, merge


def test_defaults_match_spec():
    c = TypingConfig()
    assert c.cps == 6.0
    assert c.speed_sigma == 0.35
    assert c.error_rate == 0.02
    assert c.uncorrected_rate == 0.0
    assert c.think_pause_rate == 0.03
    assert c.layout == "es"
    assert c.app_name == "Google Chrome"
    assert c.focus_guard is True
    assert c.countdown == 5
    assert c.seed is None
    assert c.pause_key == "f8"
    assert c.abort_key == "esc"


def test_merge_overrides_only_non_none_values():
    c = merge(TypingConfig(), {"cps": 9.0, "error_rate": None, "layout": "us"})
    assert c.cps == 9.0
    assert c.error_rate == 0.02
    assert c.layout == "us"


def test_merge_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown"):
        merge(TypingConfig(), {"speed": 3})


@pytest.mark.parametrize(
    "overrides",
    [{"cps": 0}, {"cps": -1}, {"error_rate": 1.5}, {"uncorrected_rate": -0.1}, {"layout": "fr"}],
)
def test_merge_validates_values(overrides):
    with pytest.raises(ValueError):
        merge(TypingConfig(), overrides)


def test_load_profile_reads_yaml(tmp_path):
    p = tmp_path / "perfil.yaml"
    p.write_text("cps: 4.5\nlayout: us\nseed: 7\n")
    assert load_profile(p) == {"cps": 4.5, "layout": "us", "seed": 7}


def test_load_profile_empty_file_is_empty_dict(tmp_path):
    p = tmp_path / "perfil.yaml"
    p.write_text("")
    assert load_profile(p) == {}


def test_profile_then_cli_precedence(tmp_path):
    p = tmp_path / "perfil.yaml"
    p.write_text("cps: 4.5\nlayout: us\n")
    c = merge(merge(TypingConfig(), load_profile(p)), {"cps": 8.0, "layout": None})
    assert c.cps == 8.0
    assert c.layout == "us"
