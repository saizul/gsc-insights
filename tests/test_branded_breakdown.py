from __future__ import annotations

import pytest

from gsc_insights.analysis import breakdown, compile_brand, is_branded, split_branded
from gsc_insights.errors import ConfigError

from .conftest import make_table

Q = make_table(
    ("query",),
    [
        ("acme widgets", 100, 400, 1.0),
        ("Acme login", 50, 100, 1.0),
        ("a c m e", 5, 50, 3.0),
        ("buy widgets", 20, 2000, 8.0),
        ("widget reviews", 10, 1000, 6.0),
    ],
)


def test_compile_empty_returns_none():
    assert compile_brand([]) is None
    assert compile_brand(["  ", ""]) is None


def test_case_insensitive_match():
    p = compile_brand(["acme"])
    assert is_branded("ACME Widgets", p) and not is_branded("buy widgets", p)


def test_no_pattern_means_not_branded():
    assert not is_branded("anything", None)


def test_regex_alternatives():
    p = compile_brand(["acme", r"a\s*c\s*m\s*e"])
    assert is_branded("a c m e", p)


def test_split_totals():
    s = split_branded(Q, ["acme"])
    assert s.branded.queries == 2 and s.branded.clicks == 150
    assert s.non_branded.clicks == 35
    assert s.branded.click_share + s.non_branded.click_share == pytest.approx(1.0)


def test_split_ctr_and_position():
    s = split_branded(Q, ["acme"])
    assert s.branded.ctr == pytest.approx(150 / 500)
    assert s.branded.position == pytest.approx(1.0)


def test_split_top_lists_sorted():
    s = split_branded(Q, ["acme"], top=1)
    assert [r.key for r in s.top_branded] == ["acme widgets"]
    assert [r.key for r in s.top_non_branded] == ["buy widgets"]


def test_split_requires_patterns():
    with pytest.raises(ConfigError, match="No brand patterns"):
        split_branded(Q, [])


def test_split_empty_table():
    s = split_branded(make_table(("query",), []), ["x"])
    assert s.branded.clicks == 0 and s.branded.ctr == 0.0


D = make_table(
    ("device",),
    [("Mobile", 60, 600, 5.0), ("Desktop", 30, 300, 4.0), ("Tablet", 10, 100, 6.0)],
)


def test_breakdown_shares_and_order():
    rows = breakdown(D)
    assert [r.key for r in rows] == ["Mobile", "Desktop", "Tablet"]
    assert rows[0].click_share == pytest.approx(0.6)
    assert sum(r.impression_share for r in rows) == pytest.approx(1.0)


def test_breakdown_other_bucket():
    rows = breakdown(D, top=2)
    assert [r.key for r in rows] == ["Mobile", "Desktop", "(other)"]
    assert rows[-1].clicks == 10


def test_breakdown_top_larger_than_table():
    assert len(breakdown(D, top=10)) == 3


def test_breakdown_empty():
    assert breakdown(make_table(("device",), [])) == []
