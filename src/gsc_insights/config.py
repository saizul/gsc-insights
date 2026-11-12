"""Configuration handling (YAML) with sensible defaults."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .errors import ConfigError

DEFAULT_CTR_CURVE: Dict[int, float] = {
    1: 0.28,
    2: 0.15,
    3: 0.10,
    4: 0.075,
    5: 0.058,
    6: 0.045,
    7: 0.036,
    8: 0.029,
    9: 0.024,
    10: 0.020,
    11: 0.014,
    12: 0.012,
    13: 0.010,
    14: 0.009,
    15: 0.008,
    16: 0.007,
    17: 0.006,
    18: 0.0055,
    19: 0.005,
    20: 0.0045,
}


@dataclass
class QuickWinsConfig:
    min_impressions: int = 100
    min_position: float = 4.0
    max_position: float = 20.0
    ctr_gap_ratio: float = 0.8
    min_extra_clicks: float = 1.0
    limit: int = 50


@dataclass
class DecliningConfig:
    min_impressions: int = 50
    min_click_drop: int = 5
    min_pct_drop: float = 20.0
    limit: int = 50


@dataclass
class CannibalisationConfig:
    min_query_impressions: int = 50
    min_page_impressions: int = 5
    min_pages: int = 2
    normalize_urls: bool = True
    exclude_branded: bool = False
    limit: int = 50


@dataclass
class MoversConfig:
    min_impressions: int = 50
    min_position_change: float = 3.0
    limit: int = 10


@dataclass
class AnomaliesConfig:
    metric: str = "clicks"
    baseline: str = "weekday"
    window: int = 28
    min_history: int = 14
    z_threshold: float = 3.0
    min_pct_change: float = 20.0
    min_spread_ratio: float = 0.05
    min_expected: float = 10.0
    fill_gaps: bool = True
    limit: int = 50


@dataclass
class BrandConfig:
    patterns: List[str] = field(default_factory=list)


@dataclass
class Config:
    title: str = "Search Console insights"
    top_n: int = 10
    ctr_curve: Dict[int, float] = field(default_factory=lambda: dict(DEFAULT_CTR_CURVE))
    brand: BrandConfig = field(default_factory=BrandConfig)
    quick_wins: QuickWinsConfig = field(default_factory=QuickWinsConfig)
    declining: DecliningConfig = field(default_factory=DecliningConfig)
    cannibalisation: CannibalisationConfig = field(default_factory=CannibalisationConfig)
    movers: MoversConfig = field(default_factory=MoversConfig)
    anomalies: AnomaliesConfig = field(default_factory=AnomaliesConfig)


_SECTIONS = {
    "brand": BrandConfig,
    "quick_wins": QuickWinsConfig,
    "declining": DecliningConfig,
    "cannibalisation": CannibalisationConfig,
    "movers": MoversConfig,
    "anomalies": AnomaliesConfig,
}


def _coerce(name: str, value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ConfigError(f"'{name}' must be true or false")
        return value
    if isinstance(default, (int, float)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"'{name}' must be a number")
        return type(default)(value)
    if isinstance(default, list):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"'{name}' must be a list of strings")
        return list(value)
    return value


def _build_section(cls: type, name: str, data: Any) -> Any:
    if data is None:
        return cls()
    if not isinstance(data, dict):
        raise ConfigError(f"Section '{name}' must be a mapping")
    obj = cls()
    known = {f.name for f in fields(cls)}
    for key, value in data.items():
        if key not in known:
            raise ConfigError(f"Unknown option '{name}.{key}'")
        setattr(obj, key, _coerce(f"{name}.{key}", value, getattr(obj, key)))
    return obj


ANOMALY_METRICS = ("clicks", "impressions", "ctr", "position")
ANOMALY_BASELINES = ("weekday", "rolling")


def validate_anomalies(cfg: AnomaliesConfig) -> AnomaliesConfig:
    """Reject anomaly settings that cannot produce meaningful results."""
    if cfg.metric not in ANOMALY_METRICS:
        raise ConfigError(f"'anomalies.metric' must be one of {', '.join(ANOMALY_METRICS)}")
    if cfg.baseline not in ANOMALY_BASELINES:
        raise ConfigError(f"'anomalies.baseline' must be one of {', '.join(ANOMALY_BASELINES)}")
    if cfg.window < 2 or not 2 <= cfg.min_history <= cfg.window:
        raise ConfigError("'anomalies' needs window >= 2 and 2 <= min_history <= window")
    if cfg.z_threshold <= 0 or cfg.min_pct_change < 0 or cfg.min_spread_ratio < 0 or cfg.limit < 0:
        raise ConfigError("'anomalies' thresholds must be positive (z_threshold) or zero or more (the rest)")
    return cfg


def parse_ctr_curve(data: Any) -> Dict[int, float]:
    if not isinstance(data, dict) or not data:
        raise ConfigError("'ctr_curve' must be a non-empty mapping of position -> CTR")
    curve: Dict[int, float] = {}
    for pos, ctr in data.items():
        try:
            position = int(pos)
            value = float(ctr)
        except (TypeError, ValueError):
            raise ConfigError(f"Invalid ctr_curve entry {pos!r}: {ctr!r}") from None
        if position < 1 or not 0 <= value <= 1:
            raise ConfigError(f"ctr_curve entry {pos!r}: position must be >= 1 and CTR a fraction in 0..1")
        curve[position] = value
    return curve


def from_dict(data: Optional[Dict[str, Any]]) -> Config:
    """Build a :class:`Config` from already-parsed YAML data."""
    cfg = Config()
    if data is None:
        return cfg
    if not isinstance(data, dict):
        raise ConfigError("Config root must be a mapping")
    for key, value in data.items():
        if key in _SECTIONS:
            setattr(cfg, key, _build_section(_SECTIONS[key], key, value))
            if key == "anomalies":
                validate_anomalies(cfg.anomalies)
        elif key == "ctr_curve":
            cfg.ctr_curve = parse_ctr_curve(value)
        elif key in ("title", "top_n"):
            setattr(cfg, key, _coerce(key, value, getattr(cfg, key)))
        else:
            raise ConfigError(f"Unknown config key '{key}'")
    return cfg


def load_config(path: str | Path | None) -> Config:
    if path is None:
        return Config()
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"Config file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {p}: {exc}") from exc
    return from_dict(data)


def expected_ctr(position: float, curve: Dict[int, float]) -> float:
    """Expected CTR at an average position, linearly interpolated on the curve.

    Positions better than the first point use the first value; positions beyond
    the last point decay proportionally to ``last_position / position``.
    """
    points = sorted(curve)
    if position <= points[0]:
        return curve[points[0]]
    if position >= points[-1]:
        return curve[points[-1]] * points[-1] / position
    i = bisect.bisect_right(points, position)
    lo, hi = points[i - 1], points[i]
    frac = (position - lo) / (hi - lo)
    return curve[lo] + (curve[hi] - curve[lo]) * frac


EXAMPLE_CONFIG = """\
# gsc-insights configuration. Every key is optional.
title: "Search Console insights"
top_n: 10

# Regular expressions (case-insensitive) that identify branded queries.
brand:
  patterns:
    - "brightleaf"
    - "bright\\\\s*leaf"

# Expected CTR by average position (fractions). Tune it with your own data.
ctr_curve:
  1: 0.28
  2: 0.15
  3: 0.10
  4: 0.075
  5: 0.058
  10: 0.020
  20: 0.0045

quick_wins:
  min_impressions: 100
  min_position: 4
  max_position: 20
  ctr_gap_ratio: 0.8        # flag when CTR < expected * ratio
  min_extra_clicks: 1
  limit: 50

declining:
  min_impressions: 50       # impressions in period A
  min_click_drop: 5
  min_pct_drop: 20
  limit: 50

cannibalisation:
  min_query_impressions: 50
  min_page_impressions: 5
  min_pages: 2
  normalize_urls: true      # ignore query strings, fragments, trailing slashes
  exclude_branded: false
  limit: 50

movers:
  min_impressions: 50
  min_position_change: 3
  limit: 10

# Daily anomalies (needs Dates.csv). Each day is compared with the days before it.
anomalies:
  metric: clicks            # clicks, impressions, ctr or position
  baseline: weekday         # weekday (day-of-week aware) or rolling (plain median)
  window: 28                # trailing days used as the baseline
  min_history: 14           # days of history needed before a day is scored
  z_threshold: 3.0          # robust z-score (median absolute deviation)
  min_pct_change: 20        # and at least this % away from expected
  min_spread_ratio: 0.05    # spread floor as a fraction of the expected value
  min_expected: 10          # skip days expecting fewer clicks/impressions
  fill_gaps: true           # dates missing from the export count as zero
  limit: 50
"""
