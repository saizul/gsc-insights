"""Top movers between two periods."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..config import MoversConfig
from .compare import Change


@dataclass
class Movers:
    gainers: List[Change] = field(default_factory=list)
    losers: List[Change] = field(default_factory=list)
    new: List[Change] = field(default_factory=list)
    lost: List[Change] = field(default_factory=list)
    position_improved: List[Change] = field(default_factory=list)
    position_dropped: List[Change] = field(default_factory=list)


def find_movers(changes: List[Change], cfg: MoversConfig, limit: int | None = None) -> Movers:
    n = limit or cfg.limit
    significant = [c for c in changes if max(c.impressions_a, c.impressions_b) >= cfg.min_impressions]
    both = [c for c in significant if c.status == "changed"]

    def top(items: List[Change], key, reverse: bool = False) -> List[Change]:
        return sorted(items, key=lambda c: (key(c), c.key), reverse=reverse)[:n]

    movers = Movers()
    movers.gainers = top([c for c in significant if c.clicks_delta > 0], lambda c: -c.clicks_delta)
    movers.losers = top([c for c in significant if c.clicks_delta < 0], lambda c: c.clicks_delta)
    movers.new = top([c for c in significant if c.status == "new"], lambda c: -c.clicks_b)
    movers.lost = top([c for c in significant if c.status == "lost"], lambda c: -c.clicks_a)
    movers.position_improved = top(
        [c for c in both if c.position_delta is not None and c.position_delta <= -cfg.min_position_change],
        lambda c: c.position_delta,  # type: ignore[return-value]
    )
    movers.position_dropped = top(
        [c for c in both if c.position_delta is not None and c.position_delta >= cfg.min_position_change],
        lambda c: -c.position_delta,  # type: ignore[operator]
    )
    return movers
