from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from gsc_insights.models import Row, Table

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

QUERIES_CSV = """Top queries,Clicks,Impressions,CTR,Position
acme widgets,120,400,30%,1.2
blue widget guide,10,1000,1%,6.5
"widget, large",3,200,1.5%,12.0
rare thing,0,5,0%,30
"""

PAGES_CSV = """Top pages,Clicks,Impressions,CTR,Position
https://example.com/,100,900,11.11%,2.0
https://example.com/guide/,33,805,4.1%,7.0
"""

DEVICES_CSV = """Device,Clicks,Impressions,CTR,Position
Mobile,90,1000,9%,5.0
Desktop,40,500,8%,4.0
Tablet,3,105,2.86%,6.0
"""

COUNTRIES_CSV = """Country,Clicks,Impressions,CTR,Position
United States,80,800,10%,4
Bangladesh,30,500,6%,5
India,15,200,7.5%,6
Japan,8,105,7.6%,7
"""

DATES_CSV = """Date,Clicks,Impressions,CTR,Position
2026-01-02,10,100,10%,4
2026-01-01,12,120,10%,4
2026-01-03,9,90,10%,5
"""

API_CSV = """query,page,clicks,impressions,ctr,position
shared term,https://example.com/a/,10,300,0.0333,5.0
shared term,https://example.com/a?utm=x,2,20,0.1,5.5
shared term,https://example.com/b/,4,200,0.02,7.0
solo term,https://example.com/a/,5,100,0.05,3.0
"""


def make_table(dims, rows):
    """rows: list of (keys tuple or str, clicks, impressions, position)."""
    out = []
    for keys, clicks, impressions, position in rows:
        keys = (keys,) if isinstance(keys, str) else tuple(keys)
        out.append(Row(keys, clicks, impressions, position))
    return Table(tuple(dims), out)


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    d = tmp_path / "export"
    d.mkdir()
    (d / "Queries.csv").write_text(QUERIES_CSV, encoding="utf-8")
    (d / "Pages.csv").write_text(PAGES_CSV, encoding="utf-8")
    (d / "Devices.csv").write_text(DEVICES_CSV, encoding="utf-8")
    (d / "Countries.csv").write_text(COUNTRIES_CSV, encoding="utf-8")
    (d / "Dates.csv").write_text(DATES_CSV, encoding="utf-8")
    (d / "Filters.csv").write_text("Filter,Value\nSearch type,Web\n", encoding="utf-8")
    return d


@pytest.fixture
def export_zip(tmp_path: Path, export_dir: Path) -> Path:
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in export_dir.iterdir():
            zf.write(f, f"site-Performance/{f.name}")
    return z


@pytest.fixture
def api_csv(tmp_path: Path) -> Path:
    p = tmp_path / "api.csv"
    p.write_text(API_CSV, encoding="utf-8")
    return p
