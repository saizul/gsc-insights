from __future__ import annotations

import pytest

from gsc_insights.errors import LoadError
from gsc_insights.loader import (
    aggregate,
    build_dataset,
    load,
    parse_csv_text,
    parse_ctr,
    parse_number,
)

from .conftest import API_CSV, EXAMPLES, make_table


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12", 12.0), ("1,234", 1234.0), (" 5.5 ", 5.5), ("", 0.0), ("-", 0.0), (None, 0.0)],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


def test_parse_number_rejects_garbage():
    with pytest.raises(LoadError):
        parse_number("abc")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("3.4%", 0.034), ("0.034", 0.034), ("12", 0.12), ("", 0.0), ("100%", 1.0)],
)
def test_parse_ctr(raw, expected):
    assert parse_ctr(raw) == pytest.approx(expected)


def test_parse_ui_queries():
    dims, rows = parse_csv_text("Top queries,Clicks,Impressions,CTR,Position\na,1,10,10%,2.5\n")
    assert dims == ("query",)
    assert rows[0].keys == ("a",)
    assert rows[0].position == 2.5


def test_parse_handles_bom_and_quotes():
    text = '﻿Top queries,Clicks,Impressions,CTR,Position\r\n"a, b",1,10,10%,2.5\r\n'
    dims, rows = parse_csv_text(text)
    assert rows[0].keys == ("a, b",)


def test_parse_semicolon_delimiter():
    dims, rows = parse_csv_text("Country;Clicks;Impressions\nUS;5;50\n")
    assert dims == ("country",)
    assert rows[0].clicks == 5


def test_parse_thousands_separators():
    _, rows = parse_csv_text('Device,Clicks,Impressions\nMobile,"1,200","34,000"\n')
    assert (rows[0].clicks, rows[0].impressions) == (1200, 34000)


def test_parse_unknown_file_returns_none():
    assert parse_csv_text("Filter,Value\nSearch type,Web\n") is None
    assert parse_csv_text("") is None


def test_parse_missing_metrics_returns_none():
    assert parse_csv_text("Top queries,Clicks\na,1\n") is None


def test_parse_skips_blank_lines():
    _, rows = parse_csv_text("Date,Clicks,Impressions\n2026-01-01,1,2\n\n,,\n")
    assert len(rows) == 1


def test_parse_short_row_errors():
    with pytest.raises(LoadError, match="line 2"):
        parse_csv_text("Date,Clicks,Impressions\n2026-01-01,1\n", "x.csv")


def test_parse_api_headers_two_dimensions():
    dims, rows = parse_csv_text(API_CSV)
    assert dims == ("query", "page")
    assert rows[0].keys[1].startswith("https://")


def test_parse_average_position_alias():
    _, rows = parse_csv_text("Page,Clicks,Impressions,Average position\n/x,1,2,3.2\n")
    assert rows[0].position == 3.2


def test_load_directory(export_dir):
    ds = load(export_dir)
    assert set(ds.tables) == {"queries", "pages", "devices", "countries", "dates"}
    assert len(ds.tables["queries"]) == 4


def test_load_zip_with_subfolder(export_zip):
    ds = load(export_zip)
    assert ds.has("queries") and ds.has("dates")


def test_load_single_csv(api_csv):
    ds = load(api_csv)
    assert ds.has("query_pages")
    assert ds.has("queries") and ds.has("pages")


def test_derived_queries_aggregate_pages(api_csv):
    ds = load(api_csv)
    shared = ds.tables["queries"].index()[("shared term",)]
    assert shared.clicks == 16
    assert shared.impressions == 520


def test_dedicated_table_beats_derived(export_dir, api_csv):
    parsed = [parse_csv_text(f.read_text()) for f in export_dir.glob("Queries.csv")]
    parsed.append(parse_csv_text(API_CSV))
    ds = build_dataset(parsed)
    assert len(ds.tables["queries"]) == 4


def test_load_missing_path(tmp_path):
    with pytest.raises(LoadError, match="does not exist"):
        load(tmp_path / "nope")


def test_load_empty_folder(tmp_path):
    with pytest.raises(LoadError, match="No CSV"):
        load(tmp_path)


def test_load_unrecognised_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(LoadError, match="expected columns"):
        load(p)


def test_load_folder_without_performance_files(tmp_path):
    (tmp_path / "Filters.csv").write_text("Filter,Value\nx,y\n")
    with pytest.raises(LoadError, match="No Performance data"):
        load(tmp_path)


def test_latin1_fallback(tmp_path):
    p = tmp_path / "Queries.csv"
    p.write_bytes("Top queries,Clicks,Impressions\ncaf\xe9,1,2\n".encode("latin-1"))
    assert load(p).tables["queries"].rows[0].keys == ("caf\xe9",)


def test_aggregate_weights_position():
    t = make_table(("query", "page"), [(("a", "p1"), 1, 100, 2.0), (("a", "p2"), 1, 300, 4.0)])
    out = aggregate(t.rows, ("query", "page"), ("query",))
    assert out.rows[0].position == pytest.approx(3.5)


def test_dataset_totals_prefers_dates(export_dir):
    ds = load(export_dir)
    assert ds.totals()[0] == 31


def test_row_ctr_zero_impressions():
    assert make_table(("query",), [("a", 0, 0, 1.0)]).rows[0].ctr == 0.0


def test_example_exports_load():
    ds = load(EXAMPLES / "period_b")
    assert ds.has("query_pages") and ds.has("devices") and len(ds.tables["queries"]) > 30
