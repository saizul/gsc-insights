"""Command line interface."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import __version__
from .analysis import (
    breakdown,
    compare,
    compile_brand,
    declining,
    find_cannibalisation,
    find_movers,
    quick_wins,
    split_branded,
)
from .config import EXAMPLE_CONFIG, Config, load_config
from .errors import ConfigError, GscInsightsError, LoadError
from .insights import build_insights
from .loader import load
from .models import Dataset, Table
from .output import COLUMNS, print_table, to_csv_text, to_json_text, to_records, write_text
from .report import write_report


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-c", "--config", help="YAML configuration file")
    p.add_argument("-f", "--format", choices=("table", "csv", "json"), default="table", help="output format")
    p.add_argument("-o", "--output", help="write results to this file (CSV unless --format json)")
    p.add_argument("--limit", type=int, help="maximum number of rows (0 = all)")


def _non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return value


def _min_impressions(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--min-impressions",
        type=_non_negative_int,
        metavar="N",
        help="ignore rows with fewer impressions (overrides the config value)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gsc-insights",
        description="Analyse Google Search Console Performance exports.",
    )
    parser.add_argument("--version", action="version", version=f"gsc-insights {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("quick-wins", help="positions 4-20 with below-expected CTR")
    p.add_argument("export", help="export folder, ZIP or CSV")
    p.add_argument("--by", choices=("queries", "pages", "query-pages"), default="queries")
    _min_impressions(p)
    _common(p)

    p = sub.add_parser("declining", help="queries/pages that lost clicks between two exports")
    p.add_argument("period_a", help="earlier export")
    p.add_argument("period_b", help="later export")
    p.add_argument("--by", choices=("queries", "pages"), default="queries")
    _min_impressions(p)
    _common(p)

    p = sub.add_parser("movers", help="biggest gainers, losers, new and lost rows")
    p.add_argument("period_a")
    p.add_argument("period_b")
    p.add_argument("--by", choices=("queries", "pages"), default="queries")
    p.add_argument(
        "--kind",
        choices=("gainers", "losers", "new", "lost", "position_improved", "position_dropped"),
        default="gainers",
    )
    _min_impressions(p)
    _common(p)

    p = sub.add_parser("cannibalisation", help="queries answered by several pages")
    p.add_argument("export", help="export with query and page columns")
    _common(p)

    p = sub.add_parser("branded", help="branded vs non-branded split")
    p.add_argument("export")
    p.add_argument("--brand", action="append", default=[], help="brand regex (repeatable)")
    _common(p)

    p = sub.add_parser("breakdown", help="device or country share of traffic")
    p.add_argument("export")
    p.add_argument("--by", choices=("devices", "countries"), default="devices")
    _common(p)

    p = sub.add_parser("report", help="write an HTML report and CSV files")
    p.add_argument("export")
    p.add_argument("--compare", metavar="PERIOD_A", help="earlier export to compare against")
    p.add_argument("--out", default="gsc-report", help="output folder (default: gsc-report)")
    p.add_argument("-c", "--config")

    p = sub.add_parser("init-config", help="print or write an example config file")
    p.add_argument("-o", "--output", help="write to this path instead of stdout")
    return parser


def _table(ds: Dataset, name: str) -> Table:
    table = ds.get(name)
    if table is None:
        have = ", ".join(sorted(ds.tables)) or "nothing"
        raise LoadError(f"Export '{ds.source}' has no {name} data (found: {have})")
    return table


def _emit(args: argparse.Namespace, title: str, kind: str, items: Sequence[Any]) -> None:
    records = to_records(items)
    columns = COLUMNS[kind]
    fmt = args.format
    if args.output:
        text = to_json_text(records) if fmt == "json" else to_csv_text(records, columns)
        path = write_text(args.output, text)
        print(f"Wrote {len(records)} rows to {path}", file=sys.stderr)
    elif fmt == "csv":
        sys.stdout.write(to_csv_text(records, columns))
    elif fmt == "json":
        sys.stdout.write(to_json_text(records))
    else:
        print_table(title, records, columns, kind)


def _limit(args: argparse.Namespace) -> Optional[int]:
    return getattr(args, "limit", None)


def _with_min_impressions(args: argparse.Namespace, section: Any) -> Any:
    """Return ``section`` with ``--min-impressions`` applied when it was given."""
    value = getattr(args, "min_impressions", None)
    return section if value is None else dataclasses.replace(section, min_impressions=value)


def cmd_quick_wins(args: argparse.Namespace, cfg: Config) -> None:
    ds = load(args.export)
    table = _table(ds, args.by.replace("-", "_"))
    wins = quick_wins(table, cfg.ctr_curve, _with_min_impressions(args, cfg.quick_wins), _limit(args))
    _emit(args, f"Quick wins ({args.by})", "quick_wins", wins)


def _changes(args: argparse.Namespace):
    a, b = load(args.period_a), load(args.period_b)
    return compare(_table(a, args.by), _table(b, args.by))


def cmd_declining(args: argparse.Namespace, cfg: Config) -> None:
    items = declining(_changes(args), _with_min_impressions(args, cfg.declining), _limit(args))
    _emit(args, f"Declining {args.by} (A -> B)", "changes", items)


def cmd_movers(args: argparse.Namespace, cfg: Config) -> None:
    movers = find_movers(_changes(args), _with_min_impressions(args, cfg.movers), _limit(args))
    _emit(args, f"Movers: {args.kind} ({args.by})", "changes", getattr(movers, args.kind))


def cmd_cannibalisation(args: argparse.Namespace, cfg: Config) -> None:
    ds = load(args.export)
    if not ds.has("query_pages"):
        raise LoadError(
            "Cannibalisation needs query + page data. Export it with the Search Analytics API "
            "or a Looker Studio/Sheets connector (columns: query, page, clicks, impressions, ...)."
        )
    brand = compile_brand(cfg.brand.patterns)
    items = find_cannibalisation(ds.tables["query_pages"], cfg.cannibalisation, brand, _limit(args))
    _emit(args, "Keyword cannibalisation", "cannibalisation", items)


def cmd_branded(args: argparse.Namespace, cfg: Config) -> None:
    ds = load(args.export)
    patterns = list(args.brand) or cfg.brand.patterns
    split = split_branded(_table(ds, "queries"), patterns, cfg.top_n)
    _emit(args, "Branded vs non-branded", "branded", split.segments())


def cmd_breakdown(args: argparse.Namespace, cfg: Config) -> None:
    ds = load(args.export)
    rows = breakdown(_table(ds, args.by), _limit(args) or None)
    _emit(args, f"Breakdown by {args.by}", "breakdown", rows)


def cmd_report(args: argparse.Namespace, cfg: Config) -> None:
    current = load(args.export)
    previous = load(args.compare) if args.compare else None
    index = write_report(build_insights(current, previous, cfg), args.out)
    print(f"Report written to {index}")


def cmd_init_config(args: argparse.Namespace, cfg: Config) -> None:
    if args.output:
        path = Path(args.output)
        if path.exists():
            raise ConfigError(f"Refusing to overwrite existing file: {path}")
        path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)
    else:
        sys.stdout.write(EXAMPLE_CONFIG)


COMMANDS: Dict[str, Callable[[argparse.Namespace, Config], None]] = {
    "quick-wins": cmd_quick_wins,
    "declining": cmd_declining,
    "movers": cmd_movers,
    "cannibalisation": cmd_cannibalisation,
    "branded": cmd_branded,
    "breakdown": cmd_breakdown,
    "report": cmd_report,
    "init-config": cmd_init_config,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(getattr(args, "config", None))
        COMMANDS[args.command](args, cfg)
    except GscInsightsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:  # pragma: no cover
        return 0
    return 0
