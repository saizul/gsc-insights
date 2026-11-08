from __future__ import annotations

from gsc_insights.analysis import quick_wins
from gsc_insights.config import DEFAULT_CTR_CURVE, QuickWinsConfig

from .conftest import make_table

CURVE = DEFAULT_CTR_CURVE


def run(rows, **kw):
    return quick_wins(make_table(("query",), rows), CURVE, QuickWinsConfig(**kw))


def test_flags_low_ctr_in_range():
    wins = run([("a", 10, 1000, 6.0)])
    assert [w.key for w in wins] == ["a"]
    assert wins[0].extra_clicks > 20


def test_ignores_good_ctr():
    assert run([("a", 80, 1000, 6.0)]) == []


def test_ignores_top_three():
    assert run([("a", 1, 5000, 2.0)]) == []


def test_ignores_beyond_position_20():
    assert run([("a", 1, 5000, 25.0)]) == []


def test_ignores_low_impressions():
    assert run([("a", 0, 50, 6.0)]) == []


def test_boundaries_inclusive():
    wins = run([("lo", 1, 2000, 4.0), ("hi", 1, 20000, 20.0)])
    assert {w.key for w in wins} == {"lo", "hi"}


def test_sorted_by_extra_clicks():
    wins = run([("small", 5, 500, 6.0), ("big", 5, 5000, 6.0)])
    assert [w.key for w in wins] == ["big", "small"]


def test_limit():
    rows = [(f"q{i}", 1, 1000 + i, 6.0) for i in range(10)]
    assert len(run(rows, limit=3)) == 3
    assert len(run(rows, limit=0)) == 10


def test_limit_argument_overrides_config():
    rows = [(f"q{i}", 1, 1000, 6.0) for i in range(5)]
    wins = quick_wins(make_table(("query",), rows), CURVE, QuickWinsConfig(), limit=2)
    assert len(wins) == 2


def test_gap_ratio_controls_sensitivity():
    row = [("a", 40, 1000, 6.0)]  # CTR 4% vs expected 4.5%
    assert run(row, ctr_gap_ratio=0.8) == []
    assert len(run(row, ctr_gap_ratio=0.95, min_extra_clicks=0)) == 1


def test_min_extra_clicks():
    assert run([("a", 8, 150, 6.0)], min_extra_clicks=50) == []


def test_as_dict_has_all_fields():
    d = run([("a", 10, 1000, 6.0)])[0].as_dict()
    assert {"key", "expected_ctr", "extra_clicks", "position"} <= set(d)
