from __future__ import annotations

import csv
import io
import json

import pytest

from gsc_insights.analysis import assign_section, summarise_sections
from gsc_insights.analysis.sections import OTHER, compile_groups, folder_section, url_path
from gsc_insights.cli import main
from gsc_insights.config import Config, from_dict
from gsc_insights.errors import ConfigError
from gsc_insights.insights import build_insights
from gsc_insights.loader import load
from gsc_insights.report import csv_exports, render_html

from .conftest import EXAMPLES, make_table

BASE = "https://example.com"

B = make_table(
    ("page",),
    [
        (f"{BASE}/", 100, 1000, 1.0),
        (f"{BASE}/blog/a/", 50, 2000, 6.0),
        (f"{BASE}/blog/b/", 30, 1000, 9.0),
        (f"{BASE}/shop/x/?ref=1", 20, 500, 4.0),
        (f"{BASE}/new-landing/", 5, 100, 12.0),
    ],
)

A = make_table(
    ("page",),
    [
        (f"{BASE}/", 90, 900, 1.0),
        (f"{BASE}/blog/a/", 80, 2000, 4.0),
        (f"{BASE}/shop/x/", 20, 500, 4.0),
        (f"{BASE}/docs/old/", 12, 300, 5.0),
    ],
)


@pytest.mark.parametrize(
    "url, depth, expected",
    [
        (f"{BASE}/", 1, "/"),
        (BASE, 1, "/"),
        (f"{BASE}/blog/post/", 1, "/blog/"),
        (f"{BASE}/blog/post/", 2, "/blog/post/"),
        (f"{BASE}/blog/2026/post/", 2, "/blog/2026/"),
        (f"{BASE}/blog/post.html", 2, "/blog/"),
        (f"{BASE}/page.html", 1, "/page.html"),
        (f"{BASE}/about/", 1, "/about/"),
        (f"{BASE}/blog/post/?utm_source=x#top", 1, "/blog/"),
        (f"{BASE}/blog/post/", 0, "/"),
        ("/relative/path/", 1, "/relative/"),
    ],
)
def test_folder_section(url, depth, expected):
    assert folder_section(url, depth) == expected


def test_url_path_decodes_percent_encoding():
    assert url_path(f"{BASE}/%E0%A6%AC%E0%A7%8D%E0%A6%B2%E0%A6%97/") == "/ব্লগ/"


def test_groups_first_match_wins_and_match_path_only():
    groups = compile_groups({"Posts": "^/blog/", "Example": "example", "All": "."})
    assert assign_section(f"{BASE}/blog/a/", groups, 1) == "Posts"
    # "example" is in the host, not the path, so it does not match.
    assert assign_section(f"{BASE}/shop/x/", groups, 1) == "All"


def test_groups_case_insensitive_and_fallbacks():
    groups = compile_groups({"Shop": "^/SHOP/"})
    assert assign_section(f"{BASE}/shop/x/", groups, 1) == "Shop"
    assert assign_section(f"{BASE}/blog/a/", groups, 1) == "/blog/"
    assert assign_section(f"{BASE}/blog/a/", groups, 1, "other") == OTHER


def test_compile_groups_errors():
    with pytest.raises(ConfigError, match="Invalid regex"):
        compile_groups({"Bad": "("})
    with pytest.raises(ConfigError, match="must not be empty"):
        compile_groups({" ": "x"})


def test_summary_totals_and_order():
    rows = summarise_sections(B)
    assert [r.section for r in rows] == ["/", "/blog/", "/shop/", "/new-landing/"]
    blog = rows[1]
    assert (blog.pages, blog.clicks, blog.impressions) == (2, 80, 3000)
    assert blog.ctr == pytest.approx(80 / 3000)
    assert blog.position == pytest.approx((6 * 2000 + 9 * 1000) / 3000)
    assert blog.top_page == f"{BASE}/blog/a/"
    assert sum(r.click_share for r in rows) == pytest.approx(1.0)
    assert sum(r.impression_share for r in rows) == pytest.approx(1.0)
    assert all(r.status == "" and r.clicks_a is None for r in rows)


def test_summary_compare_statuses_and_deltas():
    rows = {r.section: r for r in summarise_sections(B, previous=A)}
    blog = rows["/blog/"]
    assert blog.status == "changed"
    assert (blog.clicks_a, blog.clicks_delta) == (80, 0)
    assert blog.clicks_pct == pytest.approx(0.0)
    assert blog.position_delta == pytest.approx(7.0 - 4.0)
    assert rows["/new-landing/"].status == "new"
    assert rows["/new-landing/"].clicks_pct is None
    lost = rows["/docs/"]
    assert lost.status == "lost" and lost.clicks == 0 and lost.clicks_a == 12
    assert lost.clicks_delta == -12 and lost.position_a == pytest.approx(5.0)
    assert lost.position_delta is None and lost.top_page == ""


def test_summary_lost_sections_sorted_last_and_limit():
    rows = summarise_sections(B, previous=A)
    assert rows[-1].section == "/docs/"
    assert len(summarise_sections(B, previous=A, limit=2)) == 2


def test_summary_with_groups_and_other():
    rows = summarise_sections(B, {"Content": "^/blog/|^/new-"}, fallback="other")
    assert {r.section: r.pages for r in rows} == {"Content": 3, OTHER: 2}


def test_summary_rejects_bad_arguments():
    with pytest.raises(ConfigError):
        summarise_sections(B, depth=-1)
    with pytest.raises(ConfigError):
        summarise_sections(B, fallback="nope")


def test_summary_empty_table():
    assert summarise_sections(make_table(("page",), [])) == []


def test_config_sections_section():
    cfg = from_dict({"sections": {"depth": 2, "groups": {"Blog": "^/blog/"}, "fallback": "other"}})
    assert cfg.sections.depth == 2 and cfg.sections.groups == {"Blog": "^/blog/"}


@pytest.mark.parametrize(
    "section, match",
    [
        ({"depth": -1}, "0 or greater"),
        ({"fallback": "nope"}, "fallback"),
        ({"fallback": "other"}, "needs at least one"),
        ({"groups": ["^/blog/"]}, "mapping"),
        ({"groups": {"Blog": 3}}, "mapping"),
        ({"groups": {"Blog": "("}}, "Invalid regex"),
        ({"fallback": 1}, "string"),
    ],
)
def test_config_sections_validation(section, match):
    with pytest.raises(ConfigError, match=match):
        from_dict({"sections": section})


def test_report_includes_sections_with_comparison():
    cfg = Config()
    cfg.sections.groups = {"Blog": "^/blog/"}
    ins = build_insights(load(EXAMPLES / "period_b"), load(EXAMPLES / "period_a"), cfg)
    assert ins.sections and ins.sections[0].section == "Blog"
    assert all(s.status for s in ins.sections)
    html = render_html(ins)
    assert 'id="sections"' in html and "Site sections" in html and "Pos change" in html
    assert "sections.csv" in [name for name, _, _ in csv_exports(ins)]


def test_report_sections_without_comparison():
    ins = build_insights(load(EXAMPLES / "period_b"), None, Config())
    assert ins.sections and all(s.status == "" for s in ins.sections)
    assert "Pos change" not in render_html(ins)


def test_cli_sections_csv(capsys):
    assert main(["sections", str(EXAMPLES / "period_b"), "-f", "csv"]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert rows[0]["section"] == "/blog/"
    assert {r["section"] for r in rows} == {"/blog/", "/guides/", "/", "/shop/", "/about/"}


def test_cli_sections_compare_json(capsys):
    args = ["sections", str(EXAMPLES / "period_b"), "--compare", str(EXAMPLES / "period_a"), "-f", "json"]
    assert main(args) == 0
    data = {r["section"]: r for r in json.loads(capsys.readouterr().out)}
    guides = data["/guides/"]
    assert guides["status"] == "changed" and guides["clicks_delta"] < 0


def test_cli_sections_group_flag_overrides_config(capsys):
    args = [
        "sections",
        str(EXAMPLES / "period_b"),
        "--config",
        str(EXAMPLES / "config.yml"),
        "--group",
        "Learn=^/(blog|guides)/",
        "--fallback",
        "other",
        "-f",
        "json",
    ]
    assert main(args) == 0
    names = [r["section"] for r in json.loads(capsys.readouterr().out)]
    assert names == ["Learn", OTHER]


def test_cli_sections_table_output(capsys):
    args = ["sections", str(EXAMPLES / "period_b"), "--compare", str(EXAMPLES / "period_a")]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Site sections (A -> B)" in out and "clicks_delta" in out


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--group", "missing-equals"], "NAME=REGEX"),
        (["--group", "Bad=("], "Invalid regex"),
        (["--fallback", "other"], "needs at least one"),
    ],
)
def test_cli_sections_errors(capsys, extra, message):
    assert main(["sections", str(EXAMPLES / "period_b"), *extra]) == 2
    assert message in capsys.readouterr().err


def test_cli_sections_requires_pages(capsys, tmp_path):
    d = tmp_path / "only-queries"
    d.mkdir()
    (d / "Queries.csv").write_text("Top queries,Clicks,Impressions,CTR,Position\na,1,2,50%,1\n")
    assert main(["sections", str(d)]) == 2
    assert "no pages data" in capsys.readouterr().err
