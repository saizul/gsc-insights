"""Share-of-total breakdowns for dimensions such as device and country."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List

from ..models import Table, weighted_position


@dataclass
class ShareRow:
    key: str
    clicks: int
    impressions: int
    ctr: float
    position: float
    click_share: float
    impression_share: float

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def breakdown(table: Table, top: int | None = None) -> List[ShareRow]:
    """Rows sorted by clicks with their share of the table totals.

    When ``top`` truncates the list, the remainder is folded into ``(other)``.
    """
    total_clicks = sum(r.clicks for r in table)
    total_impr = sum(r.impressions for r in table)
    ordered = sorted(table.rows, key=lambda r: (-r.clicks, -r.impressions, r.key))

    def make(key: str, rows: list) -> ShareRow:
        clicks = sum(r.clicks for r in rows)
        impressions = sum(r.impressions for r in rows)
        return ShareRow(
            key,
            clicks,
            impressions,
            clicks / impressions if impressions else 0.0,
            weighted_position(rows),
            clicks / total_clicks if total_clicks else 0.0,
            impressions / total_impr if total_impr else 0.0,
        )

    if top is not None and len(ordered) > top:
        shown = [make(r.key, [r]) for r in ordered[:top]]
        shown.append(make("(other)", ordered[top:]))
        return shown
    return [make(r.key, [r]) for r in ordered]
