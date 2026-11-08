from __future__ import annotations

import pytest

from gsc_insights.analysis import compare, declining, find_movers
from gsc_insights.config import DecliningConfig, MoversConfig

from .conftest import make_table

A = make_table(
    ("query",),
    [
        ("drop", 100, 1000, 3.0),
        ("grow", 10, 500, 9.0),
        ("gone", 40, 400, 5.0),
        ("flat", 50, 600, 4.0),
        ("tiny", 4, 60, 5.0),
    ],
)
B = make_table(
    ("query",),
    [
        ("drop", 40, 900, 6.5),
        ("grow", 60, 700, 4.0),
        ("fresh", 30, 300, 8.0),
        ("flat", 51, 610, 4.1),
        ("tiny", 0, 40, 5.5),
    ],
)


def by_key(changes):
    return {c.key: c for c in changes}


def test_compare_statuses():
    c = by_key(compare(A, B))
    assert c["gone"].status == "lost" and c["gone"].clicks_b == 0
    assert c["fresh"].status == "new" and c["fresh"].clicks_pct is None
    assert c["drop"].status == "changed"


def test_compare_deltas():
    c = by_key(compare(A, B))["drop"]
    assert c.clicks_delta == -60
    assert c.clicks_pct == pytest.approx(-60.0)
    assert c.position_delta == pytest.approx(3.5)
    assert c.impressions_delta == -100


def test_position_none_when_missing():
    c = by_key(compare(A, B))
    assert c["gone"].position_b is None and c["gone"].position_delta is None
    assert c["fresh"].position_a is None


def test_declining_includes_drops_and_lost():
    keys = [c.key for c in declining(compare(A, B), DecliningConfig())]
    assert keys == ["drop", "gone"]


def test_declining_excludes_new_and_flat():
    keys = {c.key for c in declining(compare(A, B), DecliningConfig(min_click_drop=1))}
    assert "fresh" not in keys and "flat" not in keys


def test_declining_thresholds():
    cfg = DecliningConfig(min_pct_drop=70)
    assert [c.key for c in declining(compare(A, B), cfg)] == ["gone"]
    cfg = DecliningConfig(min_impressions=500)
    assert [c.key for c in declining(compare(A, B), cfg)] == ["drop"]


def test_declining_sorted_worst_first():
    out = declining(compare(A, B), DecliningConfig())
    assert out[0].clicks_delta <= out[1].clicks_delta


def test_declining_limit():
    assert len(declining(compare(A, B), DecliningConfig(), limit=1)) == 1


def test_movers_gainers_losers():
    m = find_movers(compare(A, B), MoversConfig())
    assert m.gainers[0].key == "grow"
    assert m.losers[0].key == "drop"


def test_movers_new_and_lost():
    m = find_movers(compare(A, B), MoversConfig())
    assert [c.key for c in m.new] == ["fresh"]
    assert [c.key for c in m.lost] == ["gone"]


def test_movers_position_changes():
    m = find_movers(compare(A, B), MoversConfig())
    assert [c.key for c in m.position_improved] == ["grow"]
    assert [c.key for c in m.position_dropped] == ["drop"]


def test_movers_min_impressions_filters_noise():
    m = find_movers(compare(A, B), MoversConfig(min_impressions=500))
    assert all(max(c.impressions_a, c.impressions_b) >= 500 for c in m.losers)
    assert "fresh" not in [c.key for c in m.new]


def test_movers_limit():
    assert len(find_movers(compare(A, B), MoversConfig(), limit=1).gainers) == 1


def test_compare_empty_tables():
    empty = make_table(("query",), [])
    assert compare(empty, empty) == []
