"""Branded vs non-branded query split using regular expressions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Pattern

from ..errors import ConfigError
from ..models import Row, Table, weighted_position


def compile_brand(patterns: Iterable[str]) -> Optional[Pattern[str]]:
    """Combine brand regexes into one case-insensitive pattern (or ``None``)."""
    parts = []
    for raw in patterns:
        pattern = raw.strip()
        if not pattern:
            continue
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"Invalid brand regex {raw!r}: {exc}") from exc
        parts.append(f"(?:{pattern})")
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


def is_branded(query: str, pattern: Optional[Pattern[str]]) -> bool:
    return bool(pattern and pattern.search(query))


@dataclass
class Segment:
    name: str
    queries: int
    clicks: int
    impressions: int
    ctr: float
    position: float
    click_share: float
    impression_share: float

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


@dataclass
class BrandSplit:
    branded: Segment
    non_branded: Segment
    top_branded: List[Row] = field(default_factory=list)
    top_non_branded: List[Row] = field(default_factory=list)

    def segments(self) -> List[Segment]:
        return [self.branded, self.non_branded]


def _segment(name: str, rows: List[Row], total_clicks: int, total_impr: int) -> Segment:
    clicks = sum(r.clicks for r in rows)
    impressions = sum(r.impressions for r in rows)
    return Segment(
        name=name,
        queries=len(rows),
        clicks=clicks,
        impressions=impressions,
        ctr=clicks / impressions if impressions else 0.0,
        position=weighted_position(rows),
        click_share=clicks / total_clicks if total_clicks else 0.0,
        impression_share=impressions / total_impr if total_impr else 0.0,
    )


def split_branded(table: Table, patterns: Iterable[str], top: int = 10) -> BrandSplit:
    """Split a query table into branded and non-branded segments."""
    pattern = compile_brand(patterns)
    if pattern is None:
        raise ConfigError("No brand patterns configured (use --brand or brand.patterns)")
    branded = [r for r in table if is_branded(r.keys[0], pattern)]
    other = [r for r in table if not is_branded(r.keys[0], pattern)]
    total_clicks = sum(r.clicks for r in table)
    total_impr = sum(r.impressions for r in table)
    by_clicks = lambda r: (-r.clicks, -r.impressions, r.key)  # noqa: E731
    return BrandSplit(
        branded=_segment("branded", branded, total_clicks, total_impr),
        non_branded=_segment("non-branded", other, total_clicks, total_impr),
        top_branded=sorted(branded, key=by_clicks)[:top],
        top_non_branded=sorted(other, key=by_clicks)[:top],
    )
