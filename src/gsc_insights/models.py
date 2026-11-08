"""Core data structures: rows, tables and datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class Row:
    """One line of a Performance export (one key combination)."""

    keys: Tuple[str, ...]
    clicks: int
    impressions: int
    position: float

    @property
    def key(self) -> str:
        return " | ".join(self.keys)

    @property
    def ctr(self) -> float:
        """Click-through rate as a fraction (0.034 == 3.4%)."""
        return self.clicks / self.impressions if self.impressions else 0.0


@dataclass
class Table:
    """A list of rows sharing the same dimensions."""

    dimensions: Tuple[str, ...]
    rows: List[Row] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows)

    def index(self) -> Dict[Tuple[str, ...], Row]:
        return {r.keys: r for r in self.rows}

    def totals(self) -> Tuple[int, int, float]:
        """Return (clicks, impressions, impression-weighted position)."""
        clicks = sum(r.clicks for r in self.rows)
        impressions = sum(r.impressions for r in self.rows)
        return clicks, impressions, weighted_position(self.rows)


def weighted_position(rows: Iterable[Row]) -> float:
    rows = list(rows)
    impressions = sum(r.impressions for r in rows)
    if impressions:
        return sum(r.position * r.impressions for r in rows) / impressions
    if rows:
        return sum(r.position for r in rows) / len(rows)
    return 0.0


# Preferred order when choosing the table that best represents site totals.
TOTALS_ORDER = ("dates", "devices", "countries", "pages", "queries", "query_pages")


@dataclass
class Dataset:
    """All tables found in one export (a folder, ZIP or single CSV)."""

    tables: Dict[str, Table] = field(default_factory=dict)
    source: str = ""

    def get(self, name: str) -> Optional[Table]:
        return self.tables.get(name)

    def has(self, name: str) -> bool:
        return name in self.tables

    def totals(self) -> Tuple[int, int, float]:
        for name in TOTALS_ORDER:
            table = self.tables.get(name)
            if table is not None and len(table):
                return table.totals()
        return 0, 0, 0.0
