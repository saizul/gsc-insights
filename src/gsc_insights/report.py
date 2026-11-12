"""Static HTML report (single file, no external assets) plus CSV exports."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__
from .analysis.compare import Change
from .insights import Insights
from .output import COLUMNS, to_records, write_csv

TEMPLATE_DIR = Path(__file__).parent / "templates"


def fmt_int(value: float) -> str:
    return f"{int(round(value)):,}"


def fmt_pct(fraction: float) -> str:
    return f"{fraction * 100:.2f}%"


def fmt_pos(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.1f}"


def fmt_delta(value: Optional[float], digits: int = 0) -> str:
    if value is None:
        return "-"
    return f"{value:+,.{digits}f}"


def sparkline_points(values: Sequence[float], width: int = 600, height: int = 80) -> str:
    """SVG polyline points for a series, scaled to the given box."""
    if not values:
        return ""
    if len(values) == 1:
        return f"0,{height / 2:.1f} {width},{height / 2:.1f}"
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    pad = 4
    return " ".join(
        f"{i * step:.1f},{pad + (height - 2 * pad) * (1 - (v - low) / span):.1f}"
        for i, v in enumerate(values)
    )


def _section(
    sid: str, title: str, headers: List[str], rows: List[List[str]], note: str = ""
) -> Dict[str, Any]:
    return {"id": sid, "title": title, "headers": headers, "rows": rows, "note": note}


def _change_rows(changes: Sequence[Change]) -> List[List[str]]:
    return [
        [
            c.key,
            c.status,
            fmt_int(c.clicks_a),
            fmt_int(c.clicks_b),
            fmt_delta(c.clicks_delta),
            "-" if c.clicks_pct is None else fmt_delta(c.clicks_pct, 1) + "%",
            fmt_pos(c.position_a),
            fmt_pos(c.position_b),
        ]
        for c in changes
    ]


def _metric_cell(value: float, metric: str) -> str:
    if metric == "ctr":
        return fmt_pct(value)
    if metric == "position":
        return fmt_pos(value)
    return fmt_int(value)


CHANGE_HEADERS = ["Key", "Status", "Clicks A", "Clicks B", "Change", "%", "Pos A", "Pos B"]


def build_sections(ins: Insights) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []

    def quick(label: str, items: Sequence[Any]) -> None:
        if items:
            sections.append(
                _section(
                    f"quick-wins-{label}",
                    f"Quick wins: {label}",
                    [
                        label[:-1].title(),
                        "Clicks",
                        "Impr.",
                        "CTR",
                        "Expected",
                        "Pos",
                        "Extra clicks",
                    ],
                    [
                        [
                            w.key,
                            fmt_int(w.clicks),
                            fmt_int(w.impressions),
                            fmt_pct(w.ctr),
                            fmt_pct(w.expected_ctr),
                            fmt_pos(w.position),
                            fmt_int(w.extra_clicks),
                        ]
                        for w in items
                    ],
                    "Positions 4-20 with solid impressions where CTR is below the expected curve. "
                    "Improve titles and snippets first.",
                )
            )

    quick("queries", ins.quick_wins_queries)
    quick("pages", ins.quick_wins_pages)

    if ins.anomalies:
        metric = ins.anomalies[0].metric
        as_pct = metric == "ctr"
        sections.append(
            _section(
                "anomalies",
                f"Daily anomalies: {metric}",
                ["Date", "Day", "Actual", "Expected", "Change", "%", "z", "Direction"],
                [
                    [
                        a.date,
                        a.weekday,
                        _metric_cell(a.value, metric),
                        _metric_cell(a.expected, metric),
                        fmt_delta(a.delta * 100, 2) + " pp" if as_pct else fmt_delta(a.delta, 1),
                        "-" if a.pct_change is None else fmt_delta(a.pct_change, 1) + "%",
                        fmt_delta(a.z_score, 1),
                        a.direction + (" (missing day)" if a.missing else ""),
                    ]
                    for a in ins.anomalies
                ],
                "Days that broke sharply from the trailing baseline of the days before them. "
                "Check for tracking, indexing or algorithm changes around these dates.",
            )
        )

    if ins.branded:
        seg = ins.branded.segments()
        sections.append(
            _section(
                "branded",
                "Branded vs non-branded",
                ["Segment", "Queries", "Clicks", "Impr.", "CTR", "Pos", "Click share"],
                [
                    [
                        s.name,
                        fmt_int(s.queries),
                        fmt_int(s.clicks),
                        fmt_int(s.impressions),
                        fmt_pct(s.ctr),
                        fmt_pos(s.position),
                        fmt_pct(s.click_share),
                    ]
                    for s in seg
                ],
            )
        )

    for sid, title, items in (
        ("devices", "Devices", ins.devices),
        ("countries", "Countries", ins.countries),
    ):
        if items:
            sections.append(
                _section(
                    sid,
                    title,
                    [
                        title[:-1] if title.endswith("s") else title,
                        "Clicks",
                        "Impr.",
                        "CTR",
                        "Pos",
                        "Click share",
                    ],
                    [
                        [
                            r.key,
                            fmt_int(r.clicks),
                            fmt_int(r.impressions),
                            fmt_pct(r.ctr),
                            fmt_pos(r.position),
                            fmt_pct(r.click_share),
                        ]
                        for r in items
                    ],
                )
            )

    if ins.cannibalisation:
        sections.append(
            _section(
                "cannibalisation",
                "Keyword cannibalisation",
                ["Query", "Pages", "Impr.", "Clicks", "Top page", "Top share", "Severity"],
                [
                    [
                        c.query,
                        fmt_int(len(c.pages)),
                        fmt_int(c.total_impressions),
                        fmt_int(c.total_clicks),
                        c.top_page,
                        fmt_pct(c.top_impression_share),
                        c.severity,
                    ]
                    for c in ins.cannibalisation
                ],
                "Queries where several of your pages compete in search results.",
            )
        )

    for label, items in (("queries", ins.declining_queries), ("pages", ins.declining_pages)):
        if items:
            sections.append(
                _section(f"declining-{label}", f"Declining {label}", CHANGE_HEADERS, _change_rows(items))
            )

    for label, movers in (("queries", ins.movers_queries), ("pages", ins.movers_pages)):
        if movers is None:
            continue
        for name, items in (
            ("gainers", movers.gainers),
            ("losers", movers.losers),
            ("new", movers.new),
            ("lost", movers.lost),
        ):
            if items:
                sections.append(
                    _section(
                        f"movers-{label}-{name}",
                        f"Top movers, {label}: {name}",
                        CHANGE_HEADERS,
                        _change_rows(items),
                    )
                )
    return sections


def _kpis(ins: Insights) -> List[Dict[str, str]]:
    clicks, impr, pos = ins.totals
    ctr = clicks / impr if impr else 0.0
    prev = ins.previous_totals

    def delta(now: float, before: Optional[float]) -> str:
        if before is None or not before:
            return ""
        return fmt_delta((now - before) / before * 100, 1) + "% vs period A"

    kpis = [
        {
            "label": "Clicks",
            "value": fmt_int(clicks),
            "delta": delta(clicks, prev[0] if prev else None),
        },
        {
            "label": "Impressions",
            "value": fmt_int(impr),
            "delta": delta(impr, prev[1] if prev else None),
        },
        {"label": "CTR", "value": fmt_pct(ctr), "delta": ""},
        {"label": "Avg. position", "value": fmt_pos(pos), "delta": ""},
    ]
    if prev and prev[1]:
        kpis[2]["delta"] = f"{fmt_delta((ctr - prev[0] / prev[1]) * 100, 2)} pp"
    if prev:
        kpis[3]["delta"] = f"{fmt_delta(pos - prev[2], 1)} (lower is better)"
    return kpis


def render_html(ins: Insights) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    trend_clicks = [t[1] for t in ins.trend]
    trend_impr = [t[2] for t in ins.trend]
    trend: Optional[Dict[str, Any]] = None
    if ins.trend:
        trend = {
            "start": ins.trend[0][0],
            "end": ins.trend[-1][0],
            "clicks": sparkline_points(trend_clicks),
            "impressions": sparkline_points(trend_impr),
        }
    return env.get_template("report.html.j2").render(
        title=ins.title,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        version=__version__,
        kpis=_kpis(ins),
        compare=ins.previous is not None,
        trend=trend,
        sections=build_sections(ins),
        escape=html.escape,
    )


def csv_exports(ins: Insights) -> List[Tuple[str, str, List[Any]]]:
    """(file name, column-set, items) for every non-empty result."""
    items: List[Tuple[str, str, List[Any]]] = [
        ("quick_wins_queries.csv", "quick_wins", ins.quick_wins_queries),
        ("quick_wins_pages.csv", "quick_wins", ins.quick_wins_pages),
        ("cannibalisation.csv", "cannibalisation", ins.cannibalisation),
        ("anomalies.csv", "anomalies", ins.anomalies),
        ("devices.csv", "breakdown", ins.devices),
        ("countries.csv", "breakdown", ins.countries),
        ("declining_queries.csv", "changes", ins.declining_queries),
        ("declining_pages.csv", "changes", ins.declining_pages),
    ]
    if ins.branded:
        items.append(("branded_split.csv", "branded", ins.branded.segments()))
    for label, movers in (("queries", ins.movers_queries), ("pages", ins.movers_pages)):
        if movers:
            for name in (
                "gainers",
                "losers",
                "new",
                "lost",
                "position_improved",
                "position_dropped",
            ):
                items.append((f"movers_{label}_{name}.csv", "changes", getattr(movers, name)))
    return [i for i in items if i[2]]


def write_report(ins: Insights, out_dir: str | Path) -> Path:
    """Write ``index.html`` and a ``csv/`` folder; return the HTML path."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, kind, items in csv_exports(ins):
        write_csv(root / "csv" / name, to_records(items), COLUMNS[kind])
    index = root / "index.html"
    index.write_text(render_html(ins), encoding="utf-8")
    return index
