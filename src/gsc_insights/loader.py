"""Read Google Search Console Performance exports.

Supported inputs:

* a folder containing the CSV files of a GSC UI export
  (``Queries.csv``, ``Pages.csv``, ``Countries.csv``, ``Devices.csv``, ``Dates.csv``)
* the ``.zip`` archive the GSC UI produces for the same export
* a single CSV, including Search Analytics API style files that carry several
  dimensions at once (for example ``query`` + ``page``)

Files are recognised by their header row, never by file name, so renamed files
and localised exports keep working as long as the column names are English.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .errors import LoadError
from .models import Dataset, Row, Table, weighted_position

DIMENSION_ALIASES = {
    "query": "query",
    "queries": "query",
    "top queries": "query",
    "page": "page",
    "pages": "page",
    "top pages": "page",
    "landing page": "page",
    "country": "country",
    "countries": "country",
    "device": "device",
    "devices": "device",
    "date": "date",
    "dates": "date",
}

METRIC_ALIASES = {
    "clicks": "clicks",
    "impressions": "impressions",
    "ctr": "ctr",
    "position": "position",
    "average position": "position",
    "avg position": "position",
    "avg. position": "position",
}

# Canonical dimension order used for multi-dimension files.
DIMENSION_ORDER = ("query", "page", "country", "device", "date")

TABLE_NAMES = {
    ("query",): "queries",
    ("page",): "pages",
    ("country",): "countries",
    ("device",): "devices",
    ("date",): "dates",
    ("query", "page"): "query_pages",
}

# Tables we try to derive by aggregation from wider files.
DERIVABLE = (("query", "page"), ("query",), ("page",), ("country",), ("device",), ("date",))


def parse_number(value: object) -> float:
    """Parse ``'1,234'``, ``'12.5'`` or ``''`` into a float (blank -> 0)."""
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace(" ", "")
    if text in ("", "-", "--"):
        return 0.0
    try:
        return float(text)
    except ValueError as exc:
        raise LoadError(f"Cannot read number from {value!r}") from exc


def parse_ctr(value: object) -> float:
    """Parse a CTR cell. ``'3.4%'`` and ``0.034`` both become ``0.034``."""
    text = "" if value is None else str(value).strip()
    if text.endswith("%"):
        return parse_number(text[:-1]) / 100.0
    number = parse_number(text)
    return number if number <= 1 else number / 100.0


def _norm(header: str) -> str:
    return header.replace("﻿", "").strip().lower().replace("_", " ")


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_csv_text(text: str, label: str = "CSV") -> Optional[Tuple[Tuple[str, ...], List[Row]]]:
    """Parse CSV text into ``(dimensions, rows)``.

    Returns ``None`` when the file has no recognisable dimension or metric
    columns (for example the ``Filters.csv`` file in a GSC download).
    """
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return None

    dim_cols: Dict[str, int] = {}
    metric_cols: Dict[str, int] = {}
    for idx, name in enumerate(header):
        n = _norm(name)
        if n in DIMENSION_ALIASES and DIMENSION_ALIASES[n] not in dim_cols:
            dim_cols[DIMENSION_ALIASES[n]] = idx
        elif n in METRIC_ALIASES and METRIC_ALIASES[n] not in metric_cols:
            metric_cols[METRIC_ALIASES[n]] = idx

    if not dim_cols or "clicks" not in metric_cols or "impressions" not in metric_cols:
        return None

    dims = tuple(d for d in DIMENSION_ORDER if d in dim_cols)
    rows: List[Row] = []
    for line_no, record in enumerate(reader, start=2):
        if not record or not any(cell.strip() for cell in record):
            continue
        try:
            keys = tuple(record[dim_cols[d]].strip() for d in dims)
            clicks = parse_number(record[metric_cols["clicks"]])
            impressions = parse_number(record[metric_cols["impressions"]])
            pos_idx = metric_cols.get("position")
            position = parse_number(record[pos_idx]) if pos_idx is not None else 0.0
        except IndexError:
            raise LoadError(f"{label}: line {line_no} has fewer columns than the header") from None
        except LoadError as exc:
            raise LoadError(f"{label}: line {line_no}: {exc}") from None
        rows.append(Row(keys, int(round(clicks)), int(round(impressions)), position))
    return dims, rows


def aggregate(rows: Iterable[Row], source_dims: Tuple[str, ...], target: Tuple[str, ...]) -> Table:
    """Group rows by a subset of their dimensions, summing metrics.

    Position is averaged weighted by impressions, like Search Console does.
    """
    positions = [source_dims.index(d) for d in target]
    groups: Dict[Tuple[str, ...], List[Row]] = {}
    for row in rows:
        groups.setdefault(tuple(row.keys[p] for p in positions), []).append(row)
    merged = [
        Row(
            keys,
            sum(r.clicks for r in members),
            sum(r.impressions for r in members),
            weighted_position(members),
        )
        for keys, members in groups.items()
    ]
    return Table(target, merged)


def build_dataset(parsed: Iterable[Tuple[Tuple[str, ...], List[Row]]], source: str = "") -> Dataset:
    """Combine parsed files into a :class:`Dataset`.

    Dedicated single-dimension files win over tables derived from wider files.
    """
    tables: Dict[str, Table] = {}
    derived: Dict[str, Table] = {}
    for dims, rows in parsed:
        name = TABLE_NAMES.get(dims)
        if name is not None:
            tables[name] = aggregate(rows, dims, dims)
        for target in DERIVABLE:
            if target != dims and set(target) <= set(dims):
                tname = TABLE_NAMES[target]
                if tname not in derived:
                    derived[tname] = aggregate(rows, dims, target)
    for name, table in derived.items():
        tables.setdefault(name, table)
    if not tables:
        raise LoadError("No Performance data found (no recognisable Search Console CSV files)")
    return Dataset(tables, source)


def load(path: str | Path) -> Dataset:
    """Load a folder, ZIP archive or single CSV file."""
    p = Path(path)
    if not p.exists():
        raise LoadError(f"Path does not exist: {p}")

    parsed: List[Tuple[Tuple[str, ...], List[Row]]] = []
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() == ".csv")
        if not files:
            raise LoadError(f"No CSV files in folder: {p}")
        for f in files:
            result = parse_csv_text(_decode(f.read_bytes()), f.name)
            if result:
                parsed.append(result)
    elif zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            names = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
            if not names:
                raise LoadError(f"No CSV files inside archive: {p}")
            for name in names:
                result = parse_csv_text(_decode(zf.read(name)), name)
                if result:
                    parsed.append(result)
    else:
        result = parse_csv_text(_decode(p.read_bytes()), p.name)
        if not result:
            raise LoadError(
                f"{p.name}: expected columns such as Query/Page/Country/Device/Date plus "
                "Clicks and Impressions"
            )
        parsed.append(result)
    return build_dataset(parsed, str(p))
