"""Daily traffic anomalies: days that break sharply from their recent baseline.

Each day is compared with the days before it (never with later days), so the
result matches what an alert would have said on that day. Two baselines exist:

``weekday`` (default)
    The median of the trailing window, scaled by a day-of-week factor learnt
    from that same window. Search traffic usually dips at weekends; this keeps
    every Saturday from being reported as a drop.
``rolling``
    The plain median of the trailing window.

Days already flagged are replaced by their expected value before they serve
as history, so a single outage does not distort the days that follow.

The spread is the median absolute deviation of the window's residuals
(scaled by 1.4826 so it estimates a standard deviation), floored at
``min_spread_ratio`` of the expected value so very smooth series do not turn
tiny wobbles into alerts. A day is flagged when both its robust z-score and
its percentage change pass the configured thresholds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from ..config import ANOMALY_METRICS as METRICS
from ..config import AnomaliesConfig, validate_anomalies
from ..errors import ConfigError, LoadError
from ..models import Row, Table

# Metrics that are counts; ``min_expected`` only applies to these.
COUNT_METRICS = ("clicks", "impressions")
MAD_SCALE = 1.4826
# Observations of one weekday needed before it gets its own factor.
MIN_WEEKDAY_POINTS = 3


@dataclass
class Anomaly:
    date: str
    weekday: str
    metric: str
    value: float
    expected: float
    delta: float
    pct_change: Optional[float]
    z_score: float
    direction: str
    missing: bool

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def parse_date(text: str) -> date:
    """Parse a Search Console date (``YYYY-MM-DD``)."""
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        raise LoadError(f"Cannot read date {text!r} (expected YYYY-MM-DD)") from None


def metric_value(row: Optional[Row], metric: str) -> Optional[float]:
    """Value of ``metric`` for a row; ``None`` when it is undefined.

    A missing day counts as zero clicks and impressions. CTR and position are
    undefined without impressions, so such days are skipped for those metrics.
    """
    if row is None:
        return 0.0 if metric in COUNT_METRICS else None
    if metric == "clicks":
        return float(row.clicks)
    if metric == "impressions":
        return float(row.impressions)
    if not row.impressions:
        return None
    if metric == "ctr":
        return row.ctr
    return row.position


def daily_series(
    table: Table, metric: str, fill_gaps: bool = True
) -> List[Tuple[date, Optional[float], bool]]:
    """``(day, value, missing)`` in date order.

    With ``fill_gaps`` every calendar day between the first and last date is
    present; days absent from the export get ``missing=True``.
    """
    if metric not in METRICS:
        raise ConfigError(f"Unknown metric '{metric}' (choose from {', '.join(METRICS)})")
    by_day: Dict[date, Row] = {}
    for row in table:
        day = parse_date(row.keys[0])
        if day in by_day:
            raise LoadError(f"Date {day.isoformat()} appears more than once")
        by_day[day] = row
    if not by_day:
        return []
    if fill_gaps:
        first, last = min(by_day), max(by_day)
        days = [first + timedelta(n) for n in range((last - first).days + 1)]
    else:
        days = sorted(by_day)
    return [(d, metric_value(by_day.get(d), metric), d not in by_day) for d in days]


def _mad(values: Sequence[float], centre: float) -> float:
    return median(abs(v - centre) for v in values) * MAD_SCALE


def _group(day: date) -> str:
    return "weekend" if day.weekday() >= 5 else "weekday"


def _weekday_factor(history: Sequence[Tuple[date, float]], day: date, level: float) -> float:
    """Ratio of ``day``'s weekday to the overall level.

    A median of one or two points is easily thrown by a single odd day, so a
    weekday needs ``MIN_WEEKDAY_POINTS`` observations; until then the broader
    weekday/weekend group is used.
    """
    if not level:
        return 1.0
    same = [v for d, v in history if d.weekday() == day.weekday()]
    if len(same) >= MIN_WEEKDAY_POINTS:
        return median(same) / level
    group = [v for d, v in history if _group(d) == _group(day)]
    return median(group) / level if group else 1.0


def _expected(history: Sequence[Tuple[date, float]], day: date, baseline: str) -> Tuple[float, List[float]]:
    """Expected value for ``day`` and the residuals of ``history`` against the same model."""
    level = median(v for _, v in history)
    if baseline == "rolling":
        return level, [v - level for _, v in history]
    residuals = [v - level * _weekday_factor(history, d, level) for d, v in history]
    return level * _weekday_factor(history, day, level), residuals


def find_anomalies(
    table: Table,
    cfg: AnomaliesConfig,
    metric: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Anomaly]:
    """Days whose ``metric`` deviates strongly from the trailing baseline.

    Results are sorted by date (oldest first). ``limit`` keeps the most severe
    rows (largest absolute z-score) and then restores date order.
    """
    validate_anomalies(cfg)
    metric = metric or cfg.metric
    series = daily_series(table, metric, cfg.fill_gaps)
    found: List[Anomaly] = []
    # Values used as history for later days. A flagged day is replaced by its
    # expected value so one outage does not drag down the baseline after it.
    clean: List[Tuple[date, Optional[float]]] = [(d, v) for d, v, _ in series]
    for i, (day, value, missing) in enumerate(series):
        if value is None:
            continue
        start = day - timedelta(cfg.window)
        history = [(d, v) for d, v in clean[:i] if v is not None and d >= start]
        if len(history) < cfg.min_history:
            continue
        expected, residuals = _expected(history, day, cfg.baseline)
        if metric in COUNT_METRICS and expected < cfg.min_expected:
            continue
        spread = max(_mad(residuals, median(residuals)), abs(expected) * cfg.min_spread_ratio, 1e-9)
        delta = value - expected
        z = delta / spread
        pct = delta / expected * 100 if expected else None
        if abs(z) < cfg.z_threshold:
            continue
        if pct is not None and abs(pct) < cfg.min_pct_change:
            continue
        clean[i] = (day, expected)
        found.append(
            Anomaly(
                day.isoformat(),
                day.strftime("%a"),
                metric,
                int(value) if metric in COUNT_METRICS else value,
                expected,
                delta,
                pct,
                z,
                "spike" if delta > 0 else "drop",
                missing,
            )
        )
    n = cfg.limit if limit is None else limit
    if n and len(found) > n:
        keep = sorted(found, key=lambda a: (-abs(a.z_score), a.date))[:n]
        found = sorted(keep, key=lambda a: a.date)
    return found
