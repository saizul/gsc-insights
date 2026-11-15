"""Roll pages up into site sections (URL folders or named regex groups).

A section is either a named group from the config (the first regex that matches
the URL path wins) or, for pages no group matches, the first ``depth`` folders
of the URL path, for example ``/blog/`` or ``/shop/coffee/``. The home page is ``/`` and
pages directly under the root (``/about/``) form their own section at depth 1.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional, Pattern, Tuple
from urllib.parse import unquote, urlsplit

from ..errors import ConfigError
from ..models import Row, Table, weighted_position

OTHER = "(other)"


def compile_groups(groups: Dict[str, str]) -> List[Tuple[str, Pattern[str]]]:
    """Compile ``{name: regex}`` into an ordered list of case-insensitive patterns."""
    out: List[Tuple[str, Pattern[str]]] = []
    for name, raw in groups.items():
        label = str(name).strip()
        if not label:
            raise ConfigError("Section group names must not be empty")
        try:
            out.append((label, re.compile(str(raw), re.IGNORECASE)))
        except re.error as exc:
            raise ConfigError(f"Invalid regex for section group {label!r}: {exc}") from exc
    return out


def url_path(url: str) -> str:
    """Return the decoded path of a URL (``/`` when empty)."""
    parts = urlsplit(url.strip())
    path = parts.path if parts.scheme or parts.netloc else url.strip().split("?", 1)[0].split("#", 1)[0]
    return unquote(path) or "/"


def folder_section(url: str, depth: int) -> str:
    """Section label made of the first ``depth`` path folders, e.g. ``/blog/``.

    A trailing file name (``/blog/post.html``) is not treated as a folder unless
    it is the only segment, in which case the page is its own section.
    """
    path = url_path(url)
    segments = [s for s in path.split("/") if s]
    if not segments or depth == 0:
        return "/"
    if not path.endswith("/"):
        if len(segments) == 1:
            return "/" + segments[0]
        segments = segments[:-1]
    return "/" + "/".join(segments[:depth]) + "/"


def assign_section(
    url: str, groups: List[Tuple[str, Pattern[str]]], depth: int, fallback: str = "folder"
) -> str:
    """Name of the section a page belongs to."""
    path = url_path(url)
    for name, pattern in groups:
        if pattern.search(path):
            return name
    if fallback == "other":
        return OTHER
    return folder_section(url, depth)


@dataclass
class SectionRow:
    section: str
    pages: int
    clicks: int
    impressions: int
    ctr: float
    position: float
    click_share: float
    impression_share: float
    top_page: str
    status: str = ""  # "changed", "new" or "lost" when compared; empty otherwise
    clicks_a: Optional[int] = None
    clicks_delta: Optional[int] = None
    clicks_pct: Optional[float] = None
    impressions_a: Optional[int] = None
    impressions_delta: Optional[int] = None
    position_a: Optional[float] = None
    position_delta: Optional[float] = None  # positive means the section ranks worse

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def _group_rows(
    rows: Iterable[Row], groups: List[Tuple[str, Pattern[str]]], depth: int, fallback: str
) -> Dict[str, List[Row]]:
    out: Dict[str, List[Row]] = {}
    for row in rows:
        out.setdefault(assign_section(row.keys[0], groups, depth, fallback), []).append(row)
    return out


def summarise_sections(
    pages: Table,
    groups: Optional[Dict[str, str]] = None,
    depth: int = 1,
    fallback: str = "folder",
    previous: Optional[Table] = None,
    limit: Optional[int] = None,
) -> List[SectionRow]:
    """Aggregate a pages table into sections, optionally compared with an earlier period.

    Sections are sorted by clicks in the current period. With ``previous``,
    sections that only existed in the earlier period are listed as ``lost``.
    """
    if depth < 0:
        raise ConfigError("'sections.depth' must be 0 or greater")
    if fallback not in ("folder", "other"):
        raise ConfigError("'sections.fallback' must be 'folder' or 'other'")
    compiled = compile_groups(groups or {})
    now = _group_rows(pages, compiled, depth, fallback)
    before = _group_rows(previous, compiled, depth, fallback) if previous is not None else {}
    total_clicks = sum(r.clicks for r in pages)
    total_impr = sum(r.impressions for r in pages)

    names = list(now) + [n for n in before if n not in now]
    out: List[SectionRow] = []
    for name in names:
        rows = now.get(name, [])
        clicks = sum(r.clicks for r in rows)
        impressions = sum(r.impressions for r in rows)
        top = max(rows, key=lambda r: (r.clicks, r.impressions), default=None)
        item = SectionRow(
            section=name,
            pages=len(rows),
            clicks=clicks,
            impressions=impressions,
            ctr=clicks / impressions if impressions else 0.0,
            position=weighted_position(rows) if rows else 0.0,
            click_share=clicks / total_clicks if total_clicks else 0.0,
            impression_share=impressions / total_impr if total_impr else 0.0,
            top_page=top.keys[0] if top else "",
        )
        if previous is not None:
            old = before.get(name, [])
            clicks_a = sum(r.clicks for r in old)
            impr_a = sum(r.impressions for r in old)
            item.status = "changed" if rows and old else ("new" if rows else "lost")
            item.clicks_a = clicks_a
            item.clicks_delta = clicks - clicks_a
            item.clicks_pct = (clicks - clicks_a) / clicks_a * 100.0 if clicks_a else None
            item.impressions_a = impr_a
            item.impressions_delta = impressions - impr_a
            if old:
                item.position_a = weighted_position(old)
                if rows:
                    item.position_delta = item.position - item.position_a
        out.append(item)

    out.sort(key=lambda s: (-s.clicks, -(s.clicks_a or 0), s.section))
    return out[:limit] if limit else out
