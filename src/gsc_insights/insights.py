"""Run every analysis over one (or two) datasets and collect the results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .analysis import (
    Anomaly,
    BrandSplit,
    Cannibalisation,
    Change,
    Movers,
    QuickWin,
    ShareRow,
    breakdown,
    compare,
    compile_brand,
    declining,
    find_anomalies,
    find_cannibalisation,
    find_movers,
    quick_wins,
    split_branded,
)
from .config import Config
from .models import Dataset

Totals = Tuple[int, int, float]


@dataclass
class Insights:
    title: str
    current: Dataset
    previous: Optional[Dataset] = None
    totals: Totals = (0, 0, 0.0)
    previous_totals: Optional[Totals] = None
    trend: List[Tuple[str, int, int]] = field(default_factory=list)
    anomalies: List[Anomaly] = field(default_factory=list)
    quick_wins_queries: List[QuickWin] = field(default_factory=list)
    quick_wins_pages: List[QuickWin] = field(default_factory=list)
    branded: Optional[BrandSplit] = None
    devices: List[ShareRow] = field(default_factory=list)
    countries: List[ShareRow] = field(default_factory=list)
    cannibalisation: List[Cannibalisation] = field(default_factory=list)
    declining_queries: List[Change] = field(default_factory=list)
    declining_pages: List[Change] = field(default_factory=list)
    movers_queries: Optional[Movers] = None
    movers_pages: Optional[Movers] = None


def build_insights(current: Dataset, previous: Optional[Dataset], cfg: Config) -> Insights:
    """Compute all sections the data allows; sections without data stay empty."""
    out = Insights(cfg.title, current, previous)
    out.totals = current.totals()
    if previous is not None:
        out.previous_totals = previous.totals()

    dates = current.get("dates")
    if dates:
        out.trend = [(r.key, r.clicks, r.impressions) for r in sorted(dates, key=lambda r: r.key)]
        out.anomalies = find_anomalies(dates, cfg.anomalies)

    queries = current.get("queries")
    pages = current.get("pages")
    if queries:
        out.quick_wins_queries = quick_wins(queries, cfg.ctr_curve, cfg.quick_wins)
        if cfg.brand.patterns:
            out.branded = split_branded(queries, cfg.brand.patterns, cfg.top_n)
    if pages:
        out.quick_wins_pages = quick_wins(pages, cfg.ctr_curve, cfg.quick_wins)
    if current.has("devices"):
        out.devices = breakdown(current.tables["devices"])
    if current.has("countries"):
        out.countries = breakdown(current.tables["countries"], cfg.top_n)

    qp = current.get("query_pages")
    if qp:
        out.cannibalisation = find_cannibalisation(qp, cfg.cannibalisation, compile_brand(cfg.brand.patterns))

    if previous is not None:
        for name, decl_attr, mov_attr in (
            ("queries", "declining_queries", "movers_queries"),
            ("pages", "declining_pages", "movers_pages"),
        ):
            before, after = previous.get(name), current.get(name)
            if before is None or after is None:
                continue
            changes = compare(before, after)
            setattr(out, decl_attr, declining(changes, cfg.declining))
            setattr(out, mov_attr, find_movers(changes, cfg.movers))
    return out
