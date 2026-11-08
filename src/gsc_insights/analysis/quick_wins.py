"""Quick wins: page-1/2 rankings whose CTR lags behind the expected curve."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List

from ..config import QuickWinsConfig, expected_ctr
from ..models import Table


@dataclass
class QuickWin:
    key: str
    clicks: int
    impressions: int
    ctr: float
    position: float
    expected_ctr: float
    extra_clicks: float

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def quick_wins(
    table: Table, curve: Dict[int, float], cfg: QuickWinsConfig, limit: int | None = None
) -> List[QuickWin]:
    """Find rows ranking between ``min_position`` and ``max_position`` with many
    impressions and a CTR below ``expected * ctr_gap_ratio``.

    ``extra_clicks`` estimates the clicks gained if the row reached the expected
    CTR for its current position (a title/snippet fix, not a ranking change).
    """
    wins: List[QuickWin] = []
    for row in table:
        if row.impressions < cfg.min_impressions:
            continue
        if not cfg.min_position <= row.position <= cfg.max_position:
            continue
        expected = expected_ctr(row.position, curve)
        if row.ctr >= expected * cfg.ctr_gap_ratio:
            continue
        extra = row.impressions * expected - row.clicks
        if extra < cfg.min_extra_clicks:
            continue
        wins.append(QuickWin(row.key, row.clicks, row.impressions, row.ctr, row.position, expected, extra))
    wins.sort(key=lambda w: (-w.extra_clicks, w.key))
    n = cfg.limit if limit is None else limit
    return wins[:n] if n else wins
