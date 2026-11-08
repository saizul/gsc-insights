"""Compare two periods (A = earlier, B = later) row by row."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from ..config import DecliningConfig
from ..models import Table


@dataclass
class Change:
    key: str
    status: str  # "changed", "new" (only in B) or "lost" (only in A)
    clicks_a: int
    clicks_b: int
    clicks_delta: int
    clicks_pct: Optional[float]
    impressions_a: int
    impressions_b: int
    impressions_delta: int
    position_a: Optional[float]
    position_b: Optional[float]
    position_delta: Optional[float]  # positive means the ranking got worse

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def _pct(delta: int, base: int) -> Optional[float]:
    return delta / base * 100.0 if base else None


def compare(a: Table, b: Table) -> List[Change]:
    """Return one :class:`Change` per key found in either table."""
    ia, ib = a.index(), b.index()
    changes: List[Change] = []
    for keys in list(ia) + [k for k in ib if k not in ia]:
        ra, rb = ia.get(keys), ib.get(keys)
        ca = ra.clicks if ra else 0
        cb = rb.clicks if rb else 0
        pa = ra.position if ra else None
        pb = rb.position if rb else None
        changes.append(
            Change(
                key=(ra or rb).key,  # type: ignore[union-attr]
                status="changed" if ra and rb else ("lost" if ra else "new"),
                clicks_a=ca,
                clicks_b=cb,
                clicks_delta=cb - ca,
                clicks_pct=_pct(cb - ca, ca),
                impressions_a=ra.impressions if ra else 0,
                impressions_b=rb.impressions if rb else 0,
                impressions_delta=(rb.impressions if rb else 0) - (ra.impressions if ra else 0),
                position_a=pa,
                position_b=pb,
                position_delta=(pb - pa) if pa is not None and pb is not None else None,
            )
        )
    return changes


def declining(changes: List[Change], cfg: DecliningConfig, limit: int | None = None) -> List[Change]:
    """Rows that lost a meaningful amount of clicks between the two periods."""
    out = [
        c
        for c in changes
        if c.status != "new"
        and c.impressions_a >= cfg.min_impressions
        and -c.clicks_delta >= cfg.min_click_drop
        and c.clicks_pct is not None
        and -c.clicks_pct >= cfg.min_pct_drop
    ]
    out.sort(key=lambda c: (c.clicks_delta, c.key))
    n = cfg.limit if limit is None else limit
    return out[:n] if n else out
