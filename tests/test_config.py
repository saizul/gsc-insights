from __future__ import annotations

import pytest

from gsc_insights.config import (
    DEFAULT_CTR_CURVE,
    EXAMPLE_CONFIG,
    Config,
    expected_ctr,
    from_dict,
    load_config,
    parse_ctr_curve,
)
from gsc_insights.errors import ConfigError


def test_defaults():
    cfg = Config()
    assert cfg.quick_wins.min_position == 4
    assert cfg.ctr_curve[1] == DEFAULT_CTR_CURVE[1]


def test_none_config_path_gives_defaults():
    assert load_config(None).top_n == 10


def test_override_section_values():
    cfg = from_dict({"quick_wins": {"min_impressions": 500, "ctr_gap_ratio": 0.5}})
    assert cfg.quick_wins.min_impressions == 500
    assert cfg.quick_wins.ctr_gap_ratio == 0.5
    assert cfg.quick_wins.max_position == 20


def test_int_coerced_to_float_field():
    assert from_dict({"quick_wins": {"min_position": 3}}).quick_wins.min_position == 3.0


def test_unknown_key_rejected():
    with pytest.raises(ConfigError, match="Unknown config key"):
        from_dict({"nope": 1})


def test_unknown_option_rejected():
    with pytest.raises(ConfigError, match=r"quick_wins\.bogus"):
        from_dict({"quick_wins": {"bogus": 1}})


def test_wrong_type_rejected():
    with pytest.raises(ConfigError, match="must be a number"):
        from_dict({"declining": {"min_click_drop": "lots"}})


def test_bool_not_accepted_as_number():
    with pytest.raises(ConfigError):
        from_dict({"declining": {"min_click_drop": True}})


def test_brand_patterns_must_be_strings():
    with pytest.raises(ConfigError):
        from_dict({"brand": {"patterns": [1]}})


def test_section_must_be_mapping():
    with pytest.raises(ConfigError, match="mapping"):
        from_dict({"movers": [1, 2]})


def test_empty_section_ok():
    assert from_dict({"movers": None}).movers.limit == 10


def test_root_must_be_mapping():
    with pytest.raises(ConfigError):
        from_dict(["x"])  # type: ignore[arg-type]


def test_load_config_file_and_errors(tmp_path):
    good = tmp_path / "c.yml"
    good.write_text("title: Hello\ntop_n: 5\n")
    cfg = load_config(good)
    assert (cfg.title, cfg.top_n) == ("Hello", 5)
    bad = tmp_path / "bad.yml"
    bad.write_text("title: [unclosed\n")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(bad)
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yml")


def test_example_config_parses():
    import yaml

    cfg = from_dict(yaml.safe_load(EXAMPLE_CONFIG))
    assert "bright\\s*leaf" in cfg.brand.patterns
    assert cfg.ctr_curve[20] == 0.0045


def test_custom_curve_replaces_default():
    cfg = from_dict({"ctr_curve": {1: 0.5, 10: 0.05}})
    assert cfg.ctr_curve == {1: 0.5, 10: 0.05}


@pytest.mark.parametrize("bad", [{}, {0: 0.1}, {1: 1.5}, {"x": 0.1}, [1]])
def test_bad_curve(bad):
    with pytest.raises(ConfigError):
        parse_ctr_curve(bad)


@pytest.mark.parametrize(
    ("pos", "expected"),
    [(1, 0.28), (0.4, 0.28), (4, 0.075), (4.5, (0.075 + 0.058) / 2), (20, 0.0045)],
)
def test_expected_ctr_points(pos, expected):
    assert expected_ctr(pos, DEFAULT_CTR_CURVE) == pytest.approx(expected)


def test_expected_ctr_beyond_curve_decays():
    assert expected_ctr(40, DEFAULT_CTR_CURVE) == pytest.approx(0.0045 * 20 / 40)


def test_expected_ctr_monotonic():
    values = [expected_ctr(p / 2, DEFAULT_CTR_CURVE) for p in range(2, 80)]
    assert values == sorted(values, reverse=True)
