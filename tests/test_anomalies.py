from __future__ import annotations

import csv
import dataclasses
import json
from datetime import date, timedelta

import pytest

from gsc_insights.analysis import find_anomalies
from gsc_insights.analysis.anomalies import daily_series, metric_value, parse_date
from gsc_insights.cli import main
from gsc_insights.config import AnomaliesConfig, Config, from_dict
from gsc_insights.errors import ConfigError, LoadError
from gsc_insights.insights import build_insights
from gsc_insights.loader import load
from gsc_insights.models import Row
from gsc_insights.report import csv_exports, render_html

from .conftest import EXAMPLES, make_table

START = date(2026, 3, 2)  # a Monday


def weekly_series(weeks=4, weekday=200, weekend=100, overrides=None, skip=()):
    """Dates table with a clean weekday/weekend pattern. ``overrides``: {day index: clicks}."""
    overrides = overrides or {}
    rows = []
    for i in range(weeks * 7):
        if i in skip:
            continue
        day = START + timedelta(i)
        clicks = overrides.get(i, weekend if day.weekday() >= 5 else weekday)
        rows.append((day.isoformat(), clicks, clicks * 20, 5.0))
    return make_table(("date",), rows)


def test_flat_weekly_pattern_has_no_anomalies():
    assert find_anomalies(weekly_series(), AnomaliesConfig()) == []


def test_rolling_baseline_flags_weekends_weekday_does_not():
    table = weekly_series()
    rolling = find_anomalies(table, AnomaliesConfig(baseline="rolling"))
    assert rolling and {a.weekday for a in rolling} == {"Sat", "Sun"}
    assert all(a.direction == "drop" for a in rolling)
    assert find_anomalies(table, AnomaliesConfig(baseline="weekday")) == []


def test_detects_drop_and_spike_against_weekday_baseline():
    table = weekly_series(overrides={16: 60, 23: 600})  # Wed of week 3, Wed of week 4
    found = find_anomalies(table, AnomaliesConfig())
    assert [(a.date, a.direction) for a in found] == [
        ((START + timedelta(16)).isoformat(), "drop"),
        ((START + timedelta(23)).isoformat(), "spike"),
    ]
    drop = found[0]
    assert drop.weekday == "Wed" and drop.value == 60 and drop.expected == pytest.approx(200)
    assert drop.delta == pytest.approx(-140) and drop.pct_change == pytest.approx(-70)
    assert drop.z_score < -3 and drop.metric == "clicks" and drop.missing is False


def test_only_earlier_days_form_the_baseline():
    # A spike on the last day must not change what earlier days are compared with.
    base = find_anomalies(weekly_series(overrides={16: 60}), AnomaliesConfig())
    more = find_anomalies(weekly_series(overrides={16: 60, 27: 900}), AnomaliesConfig())
    assert more[0] == base[0] and len(more) == 2


def test_flagged_days_do_not_poison_later_baselines():
    # An 8-day outage in a flat series: every outage day is a drop, and the
    # recovery is not reported as a spike even though most of the window was low.
    rows = [((START + timedelta(i)).isoformat(), 10 if 14 <= i < 22 else 100, 2000, 5.0) for i in range(28)]
    cfg = AnomaliesConfig(baseline="rolling", window=14, min_history=7)
    found = find_anomalies(make_table(("date",), rows), cfg)
    assert [a.date for a in found] == [rows[i][0] for i in range(14, 22)]
    assert {a.direction for a in found} == {"drop"}


def test_odd_warm_up_day_does_not_skew_weekday_factor():
    # Day 3 (a Thursday) is too early to score; it must not make later Thursdays look like spikes.
    assert find_anomalies(weekly_series(overrides={3: 5}), AnomaliesConfig()) == []


def test_min_history_skips_early_days():
    table = weekly_series(overrides={3: 5})  # day 3 has only 3 days of history
    assert find_anomalies(table, AnomaliesConfig()) == []
    found = find_anomalies(table, AnomaliesConfig(baseline="rolling", min_history=3))
    assert [a.date for a in found][:1] == [(START + timedelta(3)).isoformat()]


def test_pct_and_z_thresholds():
    table = weekly_series(overrides={16: 170})  # -15%
    assert find_anomalies(table, AnomaliesConfig()) == []
    found = find_anomalies(table, AnomaliesConfig(min_pct_change=10))
    assert len(found) == 1 and found[0].pct_change == pytest.approx(-15)
    assert find_anomalies(table, AnomaliesConfig(min_pct_change=10, z_threshold=50)) == []


def test_spread_floor_prevents_alerts_on_tiny_wobbles():
    table = weekly_series(overrides={16: 190})
    assert find_anomalies(table, AnomaliesConfig(min_pct_change=0)) == []
    assert find_anomalies(table, AnomaliesConfig(min_pct_change=0, min_spread_ratio=0))


def test_missing_dates_are_filled_as_zero_and_flagged():
    table = weekly_series(skip={17})
    found = find_anomalies(table, AnomaliesConfig())
    assert len(found) == 1
    gap = found[0]
    assert gap.missing and gap.value == 0 and gap.date == (START + timedelta(17)).isoformat()
    assert gap.pct_change == pytest.approx(-100)
    assert find_anomalies(table, AnomaliesConfig(fill_gaps=False)) == []


def test_missing_dates_are_skipped_for_ratio_metrics():
    table = weekly_series(skip={17})
    assert find_anomalies(table, AnomaliesConfig(), metric="ctr") == []
    assert find_anomalies(table, AnomaliesConfig(), metric="position") == []


def test_min_expected_skips_low_traffic_series():
    table = weekly_series(weekday=8, weekend=4, overrides={16: 0})
    assert find_anomalies(table, AnomaliesConfig()) == []
    assert find_anomalies(table, AnomaliesConfig(min_expected=1))


def test_position_and_ctr_metrics():
    rows = [((START + timedelta(i)).isoformat(), 100, 2000, 5.0) for i in range(28)]
    rows[20] = (rows[20][0], 100, 2000, 9.0)
    rows[22] = (rows[22][0], 20, 2000, 5.0)
    table = make_table(("date",), rows)
    pos = find_anomalies(table, AnomaliesConfig(), metric="position")
    assert [(a.date, a.direction) for a in pos] == [(rows[20][0], "spike")]
    ctr = find_anomalies(table, AnomaliesConfig(), metric="ctr")
    assert [a.date for a in ctr] == [rows[22][0]]
    assert ctr[0].value == pytest.approx(0.01) and ctr[0].expected == pytest.approx(0.05)


def test_limit_keeps_most_severe_in_date_order():
    table = weekly_series(overrides={15: 120, 16: 20, 22: 600})
    everything = find_anomalies(table, AnomaliesConfig(), limit=0)
    assert len(everything) == 3
    top = find_anomalies(table, AnomaliesConfig(), limit=2)
    assert len(top) == 2 and [a.date for a in top] == sorted(a.date for a in top)
    weakest = min(everything, key=lambda a: abs(a.z_score))
    assert weakest not in top


def test_metric_value_and_parse_date():
    row = Row(("2026-01-01",), 5, 0, 0.0)
    assert metric_value(None, "clicks") == 0.0 and metric_value(None, "ctr") is None
    assert metric_value(row, "position") is None
    assert parse_date("2026-01-05T00:00:00") == date(2026, 1, 5)
    with pytest.raises(LoadError):
        parse_date("05/01/2026")


def test_duplicate_or_bad_dates_raise():
    dup = make_table(("date",), [("2026-01-01", 1, 10, 1.0), ("2026-01-01", 2, 10, 1.0)])
    with pytest.raises(LoadError, match="more than once"):
        daily_series(dup, "clicks")
    with pytest.raises(ConfigError):
        daily_series(dup, "revenue")


@pytest.mark.parametrize(
    "section",
    [
        {"metric": "revenue"},
        {"baseline": "seasonal"},
        {"window": 1},
        {"min_history": 40},
        {"z_threshold": 0},
        {"min_pct_change": -1},
        {"bogus": 1},
    ],
)
def test_invalid_anomaly_config(section):
    with pytest.raises(ConfigError):
        from_dict({"anomalies": section})


def test_anomaly_config_from_yaml_dict():
    cfg = from_dict({"anomalies": {"metric": "impressions", "baseline": "rolling", "window": 21}})
    assert cfg.anomalies.metric == "impressions" and cfg.anomalies.window == 21
    with pytest.raises(ConfigError):
        find_anomalies(weekly_series(), dataclasses.replace(cfg.anomalies, min_history=1))


def test_example_dataset_has_one_synthetic_dip():
    found = find_anomalies(load(EXAMPLES / "period_b").tables["dates"], AnomaliesConfig())
    assert [(a.date, a.direction) for a in found] == [("2026-10-21", "drop")]
    assert find_anomalies(load(EXAMPLES / "period_a").tables["dates"], AnomaliesConfig()) == []


def test_report_includes_anomalies_section_and_csv(tmp_path):
    ins = build_insights(load(EXAMPLES / "period_b"), None, Config())
    assert [a.date for a in ins.anomalies] == ["2026-10-21"]
    html = render_html(ins)
    assert "Daily anomalies: clicks" in html and "2026-10-21" in html
    assert "anomalies.csv" in {name for name, _, _ in csv_exports(ins)}


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_anomalies_json(capsys):
    code, out, _ = run(capsys, "anomalies", EXAMPLES / "period_b", "-f", "json")
    data = json.loads(out)
    assert code == 0 and [d["date"] for d in data] == ["2026-10-21"]
    assert data[0]["direction"] == "drop" and data[0]["value"] == 60


def test_cli_anomalies_table_and_csv(capsys):
    code, out, _ = run(capsys, "anomalies", EXAMPLES / "period_b")
    assert code == 0 and "anomalies" in out and "2026-10-21" in out
    code, out, _ = run(capsys, "anomalies", EXAMPLES / "period_a", "-f", "csv")
    assert code == 0 and out.startswith("date,weekday,metric,value")
    assert list(csv.DictReader(out.splitlines())) == []


def test_cli_anomalies_overrides(capsys):
    code, out, _ = run(
        capsys, "anomalies", EXAMPLES / "period_b", "--baseline", "rolling",
        "--metric", "impressions", "--window", 7, "-f", "json",
    )  # fmt: skip
    data = json.loads(out)
    assert code == 0 and {d["metric"] for d in data} == {"impressions"}
    assert {"Sat", "Sun"} <= {d["weekday"] for d in data}
    code, out, _ = run(capsys, "anomalies", EXAMPLES / "period_b", "--threshold", 100, "-f", "json")
    assert code == 0 and json.loads(out) == []
    code, out, _ = run(capsys, "anomalies", EXAMPLES / "period_b", "--min-pct-change", 90, "-f", "json")
    assert code == 0 and json.loads(out) == []


def test_cli_anomalies_uses_config(capsys, tmp_path):
    cfg = tmp_path / "c.yml"
    cfg.write_text("anomalies:\n  baseline: rolling\n")
    code, out, _ = run(capsys, "anomalies", EXAMPLES / "period_b", "-c", cfg, "-f", "json")
    assert code == 0 and len(json.loads(out)) > 1


def test_cli_anomalies_errors(capsys, tmp_path):
    code, _, err = run(capsys, "anomalies", EXAMPLES / "period_b" / "Queries.csv")
    assert code == 2 and "no dates data" in err
    code, _, err = run(capsys, "anomalies", EXAMPLES / "period_b", "--window", 1)
    assert code == 2 and "window" in err
    (tmp_path / "Dates.csv").write_text("Date,Clicks,Impressions\nyesterday,1,2\n")
    code, _, err = run(capsys, "anomalies", tmp_path)
    assert code == 2 and "Cannot read date" in err
