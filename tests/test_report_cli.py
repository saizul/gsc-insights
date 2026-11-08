from __future__ import annotations

import csv
import json

import pytest

from gsc_insights import __version__
from gsc_insights.cli import main
from gsc_insights.config import Config
from gsc_insights.insights import build_insights
from gsc_insights.loader import load
from gsc_insights.report import (
    fmt_delta,
    fmt_int,
    fmt_pct,
    render_html,
    sparkline_points,
    write_report,
)

from .conftest import EXAMPLES


@pytest.fixture
def cfg():
    c = Config()
    c.brand.patterns = ["bright\\s*leaf"]
    return c


@pytest.fixture
def insights(cfg):
    return build_insights(load(EXAMPLES / "period_b"), load(EXAMPLES / "period_a"), cfg)


def test_fmt_helpers():
    assert fmt_int(1234.6) == "1,235"
    assert fmt_pct(0.0345) == "3.45%"
    assert fmt_delta(5) == "+5" and fmt_delta(-2.25, 1) == "-2.2" and fmt_delta(None) == "-"


def test_sparkline_points_scale():
    pts = sparkline_points([0, 10], width=100, height=50).split()
    assert pts[0].startswith("0.0,") and pts[1].startswith("100.0,")
    assert sparkline_points([]) == ""
    assert len(sparkline_points([5]).split()) == 2


def test_insights_sections_populated(insights):
    assert insights.quick_wins_queries and insights.cannibalisation
    assert insights.declining_queries and insights.branded
    assert insights.movers_queries.gainers
    assert len(insights.trend) == 28


def test_insights_without_previous(cfg):
    ins = build_insights(load(EXAMPLES / "period_a"), None, cfg)
    assert ins.declining_queries == [] and ins.movers_queries is None
    assert ins.cannibalisation == []  # period A has no query+page data


def test_html_contains_sections_and_escapes(insights):
    html = render_html(insights)
    assert "Quick wins: queries" in html and "Keyword cannibalisation" in html
    assert "Declining queries" in html and "<svg" in html


def test_html_escapes_untrusted_values(cfg, tmp_path):
    (tmp_path / "Queries.csv").write_text(
        'Top queries,Clicks,Impressions,CTR,Position\n"<script>alert(1)</script>",1,5000,0%,6\n'
    )
    html = render_html(build_insights(load(tmp_path), None, cfg))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_write_report_files(insights, tmp_path):
    index = write_report(insights, tmp_path / "out")
    assert index.exists()
    names = {p.name for p in (tmp_path / "out" / "csv").iterdir()}
    assert {"quick_wins_queries.csv", "cannibalisation.csv", "declining_queries.csv"} <= names
    with (tmp_path / "out" / "csv" / "quick_wins_queries.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows and float(rows[0]["extra_clicks"]) > 0


def test_report_empty_dataset_message(cfg, tmp_path):
    (tmp_path / "Devices.csv").write_text("Device,Clicks,Impressions\n")
    html = render_html(build_insights(load(tmp_path), None, cfg))
    assert "No sections to show" in html


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_quick_wins_csv(capsys):
    code, out, _ = run(capsys, "quick-wins", EXAMPLES / "period_b", "-f", "csv", "--limit", 5)
    assert code == 0
    rows = list(csv.DictReader(out.splitlines()))
    assert len(rows) == 5 and rows[0]["key"] == "coffee to water ratio"


def test_cli_quick_wins_table(capsys):
    code, out, _ = run(capsys, "quick-wins", EXAMPLES / "period_b", "--limit", 3)
    assert code == 0 and "Quick wins" in out


def test_cli_quick_wins_pages_json(capsys):
    code, out, _ = run(capsys, "quick-wins", EXAMPLES / "period_b", "--by", "pages", "-f", "json")
    assert code == 0 and isinstance(json.loads(out), list)


def test_cli_declining_json(capsys):
    code, out, _ = run(capsys, "declining", EXAMPLES / "period_a", EXAMPLES / "period_b", "-f", "json")
    data = json.loads(out)
    assert code == 0 and data[0]["clicks_delta"] < 0
    assert "how long to steep french press" in {d["key"] for d in data}


def test_cli_movers_kind(capsys):
    code, out, _ = run(
        capsys, "movers", EXAMPLES / "period_a", EXAMPLES / "period_b",
        "--kind", "losers", "-f", "json",
    )  # fmt: skip
    assert code == 0 and all(d["clicks_delta"] < 0 for d in json.loads(out))


def test_cli_cannibalisation_csv(capsys):
    code, out, _ = run(capsys, "cannibalisation", EXAMPLES / "period_b", "-f", "csv")
    assert code == 0 and "best coffee grinder" in out


def test_cli_cannibalisation_needs_query_pages(capsys):
    code, _, err = run(capsys, "cannibalisation", EXAMPLES / "period_a")
    assert code == 2 and "query + page" in err


def test_cli_branded_with_flag(capsys):
    code, out, _ = run(capsys, "branded", EXAMPLES / "period_b", "--brand", "bright\\s*leaf", "-f", "json")
    data = {d["name"]: d for d in json.loads(out)}
    assert code == 0 and data["branded"]["queries"] == 4


def test_cli_branded_uses_config(capsys, tmp_path):
    cfg = tmp_path / "c.yml"
    cfg.write_text("brand:\n  patterns: ['brightleaf']\n")
    code, out, _ = run(capsys, "branded", EXAMPLES / "period_b", "-c", cfg, "-f", "json")
    assert code == 0 and json.loads(out)[0]["queries"] >= 3


def test_cli_branded_without_patterns_errors(capsys):
    code, _, err = run(capsys, "branded", EXAMPLES / "period_b")
    assert code == 2 and "brand" in err


def test_cli_breakdown_devices_and_countries(capsys):
    code, out, _ = run(capsys, "breakdown", EXAMPLES / "period_b", "-f", "json")
    assert code == 0 and {d["key"] for d in json.loads(out)} == {"Mobile", "Desktop", "Tablet"}
    code, out, _ = run(
        capsys, "breakdown", EXAMPLES / "period_b", "--by", "countries", "--limit", 3, "-f", "json"
    )
    assert code == 0 and json.loads(out)[-1]["key"] == "(other)"


def test_cli_output_file(capsys, tmp_path):
    target = tmp_path / "sub" / "wins.csv"
    code, out, err = run(capsys, "quick-wins", EXAMPLES / "period_b", "-o", target)
    assert code == 0 and out == "" and "Wrote" in err
    assert target.read_text().startswith("key,clicks,impressions")


def test_cli_missing_export(capsys, tmp_path):
    code, _, err = run(capsys, "quick-wins", tmp_path / "missing")
    assert code == 2 and err.startswith("error:")


def test_cli_missing_table(capsys, tmp_path):
    (tmp_path / "Devices.csv").write_text("Device,Clicks,Impressions\nMobile,1,2\n")
    code, _, err = run(capsys, "quick-wins", tmp_path)
    assert code == 2 and "no queries data" in err


def test_cli_bad_config(capsys, tmp_path):
    cfg = tmp_path / "c.yml"
    cfg.write_text("bogus: 1\n")
    code, _, err = run(capsys, "quick-wins", EXAMPLES / "period_b", "-c", cfg)
    assert code == 2 and "bogus" in err


def test_cli_report(capsys, tmp_path):
    code, out, _ = run(
        capsys, "report", EXAMPLES / "period_b", "--compare", EXAMPLES / "period_a",
        "--out", tmp_path / "r", "-c", EXAMPLES / "config.yml",
    )  # fmt: skip
    assert code == 0 and (tmp_path / "r" / "index.html").exists()
    assert "Report written" in out


def test_cli_init_config(capsys, tmp_path):
    code, out, _ = run(capsys, "init-config")
    assert code == 0 and "quick_wins:" in out
    target = tmp_path / "gsc.yml"
    assert run(capsys, "init-config", "-o", target)[0] == 0
    assert run(capsys, "init-config", "-o", target)[0] == 2  # refuses to overwrite


def test_cli_works_on_zip(capsys, export_zip):
    code, out, _ = run(capsys, "breakdown", export_zip, "-f", "csv")
    assert code == 0 and "Mobile" in out
