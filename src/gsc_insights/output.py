"""Console, CSV and JSON output helpers."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List, Sequence

from rich.console import Console
from rich.table import Table as RichTable

from .analysis.anomalies import Anomaly
from .analysis.branded import Segment
from .analysis.breakdown import ShareRow
from .analysis.compare import Change
from .analysis.quick_wins import QuickWin

COLUMNS: Dict[str, List[str]] = {
    "quick_wins": [f.name for f in fields(QuickWin)],
    "changes": [f.name for f in fields(Change)],
    "breakdown": [f.name for f in fields(ShareRow)],
    "branded": [f.name for f in fields(Segment)],
    "anomalies": [f.name for f in fields(Anomaly)],
    "cannibalisation": [
        "query",
        "pages",
        "total_clicks",
        "total_impressions",
        "top_page",
        "top_impression_share",
        "severity",
        "advice",
        "competing_pages",
    ],
}


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    return value


def to_records(items: Sequence[Any]) -> List[Dict[str, Any]]:
    return [{k: _clean(v) for k, v in item.as_dict().items()} for item in items]


def to_csv_text(records: List[Dict[str, Any]], columns: List[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for rec in records:
        writer.writerow({k: ("" if rec.get(k) is None else rec.get(k)) for k in columns})
    return buf.getvalue()


def to_json_text(records: List[Dict[str, Any]]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def write_csv(path: str | Path, records: List[Dict[str, Any]], columns: List[str]) -> Path:
    return write_text(path, to_csv_text(records, columns))


def write_text(path: str | Path, text: str) -> Path:
    """Write UTF-8 text without newline translation, creating parent folders."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return p


DISPLAY: Dict[str, List[str]] = {
    "anomalies": [
        "date",
        "weekday",
        "value",
        "expected",
        "delta",
        "pct_change",
        "z_score",
        "direction",
        "missing",
    ],
    "changes": [
        "key",
        "status",
        "clicks_a",
        "clicks_b",
        "clicks_delta",
        "clicks_pct",
        "position_a",
        "position_b",
    ],
    "cannibalisation": [
        "query",
        "pages",
        "total_impressions",
        "top_impression_share",
        "severity",
        "top_page",
    ],
}


def print_table(title: str, records: List[Dict[str, Any]], columns: List[str], kind: str = "") -> None:
    columns = DISPLAY.get(kind, columns)
    console = Console()
    if not console.is_terminal and console.width < 120:
        console = Console(width=120)
    table = RichTable(title=title, show_lines=False)
    for col in columns:
        numeric = bool(records) and isinstance(records[0].get(col), (int, float))
        table.add_column(col, justify="right" if numeric else "left", overflow="fold")
    for rec in records:
        table.add_row(*["" if rec.get(c) is None else _fmt(rec[c]) for c in columns])
    console.print(table)
    if not records:
        console.print("[dim]No rows matched the current thresholds.[/dim]")


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".") if abs(value) < 1 else f"{value:,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)
