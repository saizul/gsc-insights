from __future__ import annotations

import pytest

from gsc_insights.analysis import compile_brand, find_cannibalisation, normalize_url
from gsc_insights.config import CannibalisationConfig
from gsc_insights.errors import ConfigError

from .conftest import make_table


def qp(rows):
    return make_table(("query", "page"), [((q, p), c, i, pos) for q, p, c, i, pos in rows])


ROWS = [
    ("split", "https://x.com/a/", 10, 500, 5.0),
    ("split", "https://x.com/b/", 8, 450, 6.0),
    ("dominant", "https://x.com/a/", 50, 900, 3.0),
    ("dominant", "https://x.com/b/", 1, 40, 12.0),
    ("single", "https://x.com/a/", 5, 300, 4.0),
]


def test_finds_multi_page_queries_only():
    found = find_cannibalisation(qp(ROWS), CannibalisationConfig())
    assert {c.query for c in found} == {"split", "dominant"}


def test_severity_and_order():
    found = find_cannibalisation(qp(ROWS), CannibalisationConfig())
    assert found[0].query == "split" and found[0].severity == "high"
    assert found[1].severity == "low"


def test_top_page_by_impressions():
    c = find_cannibalisation(qp(ROWS), CannibalisationConfig())[0]
    assert c.top_page == "https://x.com/a"
    assert c.top_impression_share == pytest.approx(500 / 950)


def test_normalises_duplicate_urls():
    rows = [
        ("q", "https://x.com/a/", 1, 100, 5.0),
        ("q", "https://X.com/a?utm_source=z", 1, 100, 7.0),
    ]
    assert find_cannibalisation(qp(rows), CannibalisationConfig()) == []
    found = find_cannibalisation(qp(rows), CannibalisationConfig(normalize_urls=False))
    assert len(found) == 1


def test_merged_page_position_is_weighted():
    rows = [
        ("q", "https://x.com/a/", 1, 100, 4.0),
        ("q", "https://x.com/a", 1, 300, 8.0),
        ("q", "https://x.com/b", 1, 200, 5.0),
    ]
    page_a = find_cannibalisation(qp(rows), CannibalisationConfig())[0].pages[0]
    assert page_a.impressions == 400 and page_a.position == pytest.approx(7.0)


def test_min_page_impressions_filters_tiny_pages():
    rows = [("q", "https://x.com/a", 5, 500, 3.0), ("q", "https://x.com/b", 0, 3, 9.0)]
    assert find_cannibalisation(qp(rows), CannibalisationConfig()) == []


def test_min_query_impressions():
    rows = [("q", "https://x.com/a", 1, 20, 3.0), ("q", "https://x.com/b", 1, 20, 9.0)]
    assert find_cannibalisation(qp(rows), CannibalisationConfig(min_query_impressions=100)) == []


def test_exclude_branded():
    rows = [("acme shop", "https://x.com/a", 1, 100, 1.0), ("acme shop", "https://x.com/b", 1, 100, 2.0)]
    brand = compile_brand(["acme"])
    assert find_cannibalisation(qp(rows), CannibalisationConfig(exclude_branded=True), brand) == []
    assert len(find_cannibalisation(qp(rows), CannibalisationConfig(), brand)) == 1


def test_three_pages_raise_severity():
    rows = [("q", f"https://x.com/{p}", 1, i, 5.0) for p, i in (("a", 100), ("b", 60), ("c", 60))]
    assert find_cannibalisation(qp(rows), CannibalisationConfig())[0].severity == "high"


def test_as_dict_lists_competing_pages():
    d = find_cannibalisation(qp(ROWS), CannibalisationConfig())[0].as_dict()
    assert d["pages"] == 2 and "https://x.com/b" in d["competing_pages"]


def test_limit():
    assert len(find_cannibalisation(qp(ROWS), CannibalisationConfig(), limit=1)) == 1


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("https://Example.com/Path/?a=1#frag", "https://example.com/Path"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/a/b/", "https://example.com/a/b"),
    ],
)
def test_normalize_url(raw, clean):
    assert normalize_url(raw) == clean


def test_invalid_brand_regex():
    with pytest.raises(ConfigError):
        compile_brand(["(unclosed"])
