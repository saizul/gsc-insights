"""Keyword cannibalisation: one query ranking with several of your pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern
from urllib.parse import urlsplit, urlunsplit

from ..config import CannibalisationConfig
from ..models import Table
from .branded import is_branded


def normalize_url(url: str) -> str:
    """Drop query string, fragment and trailing slash; lowercase scheme and host."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


@dataclass
class PageShare:
    page: str
    clicks: int
    impressions: int
    position: float


@dataclass
class Cannibalisation:
    query: str
    total_clicks: int
    total_impressions: int
    pages: List[PageShare]
    top_page: str
    top_impression_share: float
    severity: str
    advice: str

    def as_dict(self) -> Dict[str, object]:
        detail = "; ".join(
            f"{p.page} (pos {p.position:.1f}, {p.clicks} clicks, {p.impressions} impr)" for p in self.pages
        )
        return {
            "query": self.query,
            "pages": len(self.pages),
            "total_clicks": self.total_clicks,
            "total_impressions": self.total_impressions,
            "top_page": self.top_page,
            "top_impression_share": self.top_impression_share,
            "severity": self.severity,
            "advice": self.advice,
            "competing_pages": detail,
        }


def _severity(top_share: float, pages: int) -> str:
    split = 1.0 - top_share
    if split >= 0.4 or (pages >= 3 and split >= 0.3):
        return "high"
    if split >= 0.2:
        return "medium"
    return "low"


_ADVICE = {
    "high": "Impressions are split across pages: merge or redirect, or differentiate the intent.",
    "medium": "Review the competing pages and add internal links to the preferred URL.",
    "low": "One page dominates; keep an eye on it and link to the main page.",
}


def find_cannibalisation(
    table: Table,
    cfg: CannibalisationConfig,
    brand: Optional[Pattern[str]] = None,
    limit: int | None = None,
) -> List[Cannibalisation]:
    """Detect queries answered by two or more pages in a ``query_pages`` table."""
    grouped: Dict[str, Dict[str, List]] = {}
    for row in table:
        query, page = row.keys[0], row.keys[1]
        if cfg.exclude_branded and is_branded(query, brand):
            continue
        if row.impressions < cfg.min_page_impressions:
            continue
        key = normalize_url(page) if cfg.normalize_urls else page
        grouped.setdefault(query, {}).setdefault(key, []).append(row)

    found: List[Cannibalisation] = []
    for query, pages in grouped.items():
        if len(pages) < cfg.min_pages:
            continue
        shares = []
        for page, rows in pages.items():
            impressions = sum(r.impressions for r in rows)
            position = sum(r.position * r.impressions for r in rows) / impressions
            shares.append(PageShare(page, sum(r.clicks for r in rows), impressions, position))
        shares.sort(key=lambda p: (-p.impressions, -p.clicks, p.page))
        total_impr = sum(p.impressions for p in shares)
        if total_impr < cfg.min_query_impressions:
            continue
        top_share = shares[0].impressions / total_impr
        severity = _severity(top_share, len(shares))
        found.append(
            Cannibalisation(
                query=query,
                total_clicks=sum(p.clicks for p in shares),
                total_impressions=total_impr,
                pages=shares,
                top_page=shares[0].page,
                top_impression_share=top_share,
                severity=severity,
                advice=_ADVICE[severity],
            )
        )
    order = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda c: (order[c.severity], -c.total_impressions, c.query))
    n = cfg.limit if limit is None else limit
    return found[:n] if n else found
