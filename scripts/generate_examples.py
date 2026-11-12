"""Generate the synthetic example exports in ./examples (fictional coffee shop).

All numbers are invented. Run:  python scripts/generate_examples.py
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gsc_insights.config import DEFAULT_CTR_CURVE, expected_ctr  # noqa: E402

SITE = "https://www.brightleafcoffee.example"

# query, page, impressions A, position A, impressions B, position B, CTR factor vs curve
QUERIES = [
    ("brightleaf coffee", "/", 900, 1.1, 1000, 1.1, 1.3),
    ("bright leaf coffee roasters", "/", 380, 1.4, 420, 1.3, 1.2),
    ("brightleaf coffee discount code", "/shop/starter-bundle/", 160, 2.2, 170, 2.0, 1.1),
    ("pour over coffee", "/guides/pour-over-coffee/", 4200, 6.8, 4600, 6.2, 0.55),
    ("how to make pour over coffee", "/guides/pour-over-coffee/", 1800, 5.1, 2000, 4.6, 0.7),
    ("v60 brew ratio", "/guides/pour-over-coffee/", 950, 8.4, 1050, 7.9, 0.5),
    ("french press ratio", "/guides/french-press/", 3100, 4.8, 3000, 5.4, 0.6),
    ("how long to steep french press", "/guides/french-press/", 2600, 3.2, 2000, 5.9, 0.9),
    ("french press vs drip", "/guides/french-press/", 700, 9.2, 640, 9.9, 0.7),
    ("cold brew coffee recipe", "/guides/cold-brew/", 5200, 7.4, 5400, 7.1, 0.5),
    ("cold brew concentrate ratio", "/guides/cold-brew/", 1500, 11.5, 1700, 10.8, 0.6),
    ("how long does cold brew last", "/guides/cold-brew/", 2300, 4.1, 1700, 7.5, 0.8),
    ("espresso at home", "/guides/espresso-at-home/", 3400, 12.9, 3600, 12.1, 0.7),
    (
        "best espresso beans for beginners",
        "/blog/best-espresso-beans/",
        1200,
        14.5,
        1500,
        13.2,
        0.6,
    ),
    ("how to dial in espresso", "/guides/espresso-at-home/", 850, 9.8, 900, 9.1, 0.6),
    ("best coffee grinder", "/blog/best-coffee-grinders/", 8800, 9.6, 8300, 10.4, 0.55),
    ("best burr grinder under 100", "/blog/best-coffee-grinders/", 2100, 6.3, 2300, 5.7, 0.65),
    ("burr vs blade grinder", "/blog/best-coffee-grinders/", 1300, 5.5, 1250, 5.2, 0.8),
    ("coffee to water ratio", "/blog/coffee-to-water-ratio/", 9500, 5.9, 9700, 5.6, 0.6),
    ("coffee ratio calculator", "/blog/coffee-to-water-ratio/", 2800, 3.9, 3300, 3.4, 0.9),
    ("how much coffee per cup", "/blog/coffee-to-water-ratio/", 3900, 7.7, 3600, 8.6, 0.5),
    ("aeropress recipes", "/blog/aeropress-recipes/", 2700, 8.2, 2900, 7.6, 0.5),
    ("inverted aeropress method", "/blog/aeropress-recipes/", 640, 4.4, 540, 6.8, 0.8),
    ("moka pot instructions", "/blog/moka-pot-guide/", 1900, 6.6, 1800, 7.0, 0.6),
    ("why is my moka pot bitter", "/blog/moka-pot-guide/", 760, 5.2, 560, 8.9, 0.8),
    ("ethiopia yirgacheffe coffee", "/shop/ethiopia-yirgacheffe/", 1700, 4.3, 1900, 4.0, 0.9),
    ("buy colombian coffee beans", "/shop/colombia-huila/", 1100, 11.2, 1250, 10.4, 0.6),
    ("single origin coffee subscription", "/shop/starter-bundle/", 1450, 13.8, 1600, 12.5, 0.6),
    ("light roast vs dark roast", "/blog/light-vs-dark-roast/", 4700, 8.9, 4400, 9.7, 0.55),
    (
        "does dark roast have more caffeine",
        "/blog/light-vs-dark-roast/",
        3600,
        4.9,
        3900,
        4.5,
        0.75,
    ),
    ("coffee bloom meaning", "/guides/pour-over-coffee/", 1250, 6.1, 1100, 6.0, 0.7),
    ("water temperature for coffee", "/blog/coffee-to-water-ratio/", 2200, 8.0, 2250, 7.8, 0.6),
    ("how to store coffee beans", "/blog/storing-coffee-beans/", 3300, 5.6, 3500, 5.1, 0.7),
    ("coffee bean freshness date", "/blog/storing-coffee-beans/", 540, 10.9, 700, 9.4, 0.6),
    ("chemex vs v60", "/guides/pour-over-coffee/", 1600, 7.2, 1650, 7.3, 0.55),
    ("turkish coffee grind size", "/blog/best-coffee-grinders/", 410, 12.3, 480, 11.6, 0.6),
    ("decaf coffee swiss water process", "/blog/decaf-guide/", 880, 15.7, 940, 14.9, 0.7),
    ("is cold brew stronger than hot coffee", "/guides/cold-brew/", 1050, 3.6, 620, 8.1, 0.9),
    ("coffee roast levels explained", "/blog/light-vs-dark-roast/", 2050, 9.1, 2150, 8.7, 0.6),
    ("brightleaf subscription cancel", "/about/", 90, 3.1, 110, 3.0, 1.0),
    ("tiny long tail query one", "/blog/decaf-guide/", 12, 18.0, 14, 17.0, 0.5),
]

# Extra (query, page) pairs to show cannibalisation: share of impressions given to the extra page.
EXTRA_PAGES = {
    "pour over coffee": [("/blog/aeropress-recipes/", 0.30, 3.0)],
    "cold brew coffee recipe": [("/blog/storing-coffee-beans/", 0.18, 5.0)],
    "best coffee grinder": [
        ("/blog/best-espresso-beans/", 0.12, 8.0),
        ("/guides/espresso-at-home/", 0.22, 6.0),
    ],
    "coffee to water ratio": [("/guides/french-press/", 0.38, 2.5)],
    "french press ratio": [("/blog/coffee-to-water-ratio/", 0.45, 1.5)],
    "light roast vs dark roast": [("/blog/coffee-roast-levels/", 0.05, 6.0)],
}

COUNTRIES = [
    ("United States", 0.34),
    ("United Kingdom", 0.12),
    ("India", 0.11),
    ("Canada", 0.07),
    ("Australia", 0.06),
    ("Germany", 0.05),
    ("Bangladesh", 0.03),
    ("Brazil", 0.03),
    ("Netherlands", 0.03),
    ("Other", 0.16),
]
DEVICES = [("Mobile", 0.58, 1.15, 0.95), ("Desktop", 0.37, 0.85, 1.0), ("Tablet", 0.05, 0.8, 1.05)]


# Index into period B's daily rows that gets a sharp, synthetic traffic dip.
ANOMALY_DAY = 20


def clicks_for(rng: random.Random, impr: int, pos: float, factor: float) -> int:
    noise = 0.92 + rng.random() * 0.16
    return int(round(impr * expected_ctr(pos, DEFAULT_CTR_CURVE) * factor * noise))


def pct(clicks: int, impr: int) -> str:
    return f"{(clicks / impr * 100 if impr else 0):.2f}%"


def write_ui(path: Path, header: str, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow([header, "Clicks", "Impressions", "CTR", "Position"])
        for key, clicks, impr, pos in rows:
            w.writerow([key, clicks, impr, pct(clicks, impr), f"{pos:.1f}"])


def build_period(name: str, start: date, use_b: bool, seed: int) -> None:
    rng = random.Random(seed)
    out = ROOT / "examples" / name
    out.mkdir(parents=True, exist_ok=True)

    qrows, qp_rows, page_acc = [], [], {}
    for q, page, ia, pa, ib, pb, factor in QUERIES:
        impr, pos = (ib, pb) if use_b else (ia, pa)
        extras = EXTRA_PAGES.get(q, [])
        main_share = 1.0 - sum(s for _, s, _ in extras)
        main_impr = int(impr * main_share)
        parts = [(page, main_impr, pos, factor)] + [
            (p, int(impr * s), pos + dp, factor * 0.6) for p, s, dp in extras
        ]
        total_clicks = 0
        total_impr = 0
        for p, pi, pp, pf in parts:
            c = clicks_for(rng, pi, pp, pf)
            qp_rows.append((q, SITE + p, c, pi, pp))
            total_clicks += c
            total_impr += pi
            acc = page_acc.setdefault(p, [0, 0, 0.0])
            acc[0] += c
            acc[1] += pi
            acc[2] += pp * pi
        qrows.append((q, total_clicks, total_impr, pos))

    write_ui(out / "Queries.csv", "Top queries", sorted(qrows, key=lambda r: -r[1]))
    prow = [(SITE + p, int(c * 1.3), int(i * 1.25), s / i) for p, (c, i, s) in page_acc.items()]
    write_ui(out / "Pages.csv", "Top pages", sorted(prow, key=lambda r: -r[1]))

    clicks_total = sum(r[1] for r in prow)
    impr_total = sum(r[2] for r in prow)
    avg_pos = sum(r[3] * r[2] for r in prow) / impr_total

    crow = []
    for country, share in COUNTRIES:
        i = int(impr_total * share)
        c = int(clicks_total * share * (1.2 if country in ("United States", "United Kingdom") else 0.9))
        crow.append((country, c, i, avg_pos + rng.random()))
    write_ui(out / "Countries.csv", "Country", sorted(crow, key=lambda r: -r[1]))

    drow = []
    for device, share, cf, pf in DEVICES:
        drow.append((device, int(clicks_total * share * cf), int(impr_total * share), avg_pos * pf))
    write_ui(out / "Devices.csv", "Device", sorted(drow, key=lambda r: -r[1]))

    days = 28
    weights = [
        1.0 + 0.25 * (1 if (start + timedelta(d)).weekday() < 5 else -1) + rng.random() * 0.2
        for d in range(days)
    ]
    wsum = sum(weights)
    trend = 1.0
    daily = []
    for d in range(days):
        trend *= 1.002 if use_b else 0.999
        w = weights[d] / wsum * trend
        daily.append(
            (
                (start + timedelta(d)).isoformat(),
                int(clicks_total * w),
                int(impr_total * w),
                avg_pos + rng.random() * 0.4 - 0.2,
            )
        )
    if use_b:
        # A one-day dip (think broken tracking or a deploy gone wrong) for `anomalies`.
        day, clicks, impr, pos = daily[ANOMALY_DAY]
        daily[ANOMALY_DAY] = (day, int(clicks * 0.45), int(impr * 0.6), pos)
    write_ui(out / "Dates.csv", "Date", daily)

    if use_b:
        # Search Analytics API style export with query + page columns.
        with (out / "QueryPages.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["query", "page", "clicks", "impressions", "ctr", "position"])
            for q, page, c, i, p in sorted(qp_rows, key=lambda r: (-r[3], r[0])):
                w.writerow([q, page, c, i, f"{(c / i if i else 0):.4f}", f"{p:.2f}"])


def main() -> None:
    build_period("period_a", date(2026, 9, 1), use_b=False, seed=11)
    build_period("period_b", date(2026, 10, 1), use_b=True, seed=12)
    config = ROOT / "examples" / "config.yml"
    from gsc_insights.config import EXAMPLE_CONFIG

    config.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    print("Examples written to", ROOT / "examples")


if __name__ == "__main__":
    main()
