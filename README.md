# gsc-insights

[![CI](https://github.com/saizul/gsc-insights/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/gsc-insights/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Turn Google Search Console **Performance** exports into things you can act on:
quick wins, declining queries and pages, keyword cannibalisation, a branded vs
non-branded split, top movers and device/country breakdowns. Everything runs
locally on the CSV files you download. No API keys, no OAuth, no uploads.

Built by [Saizul Amin](https://saizul.com), a WordPress developer and SEO specialist.

## What you get

| Command | Answers |
| --- | --- |
| `quick-wins` | Which queries/pages sit at positions 4-20 with lots of impressions but a CTR below what that position normally earns? |
| `declining` | Which queries/pages lost clicks between period A and period B? |
| `movers` | Biggest gainers, losers, new, lost, and ranking movers between two periods. |
| `cannibalisation` | Which queries are served by two or more of your pages? |
| `branded` | How much traffic comes from brand searches (regex-based)? |
| `breakdown` | How are clicks and impressions split by device or country? |
| `report` | All of the above as one HTML file plus CSV files. |

## Install

```bash
pip install .            # from a clone
# or, for development
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Exporting from Search Console

1. Open Search Console, choose your property and go to **Performance > Search results**.
2. Set the date range (for comparisons, export two ranges of equal length, for example
   the last 28 days and the 28 days before that).
3. Click **Export > Download .csv** (or **.zip**, which contains one CSV per tab).
   You get `Queries.csv`, `Pages.csv`, `Countries.csv`, `Devices.csv` and `Dates.csv`.
4. Point gsc-insights at the unzipped folder, the `.zip` itself, or a single CSV.

The UI export contains one dimension per file, so it cannot tell which page ranks for which
query. **Cannibalisation needs query + page data.** Get it from the Search Analytics API, a
Looker Studio or Google Sheets connector, or any tool that exports `query,page,clicks,impressions,ctr,position`.
Put that CSV in the same folder (any file name) or pass it directly.

Files are recognised by their header row, so renamed files work. Accepted column names include
`Top queries`/`query`, `Top pages`/`page`, `Country`, `Device`, `Date`, `Clicks`, `Impressions`,
`CTR` (`3.4%` or `0.034`) and `Position`/`Average position`.

## Quick start

The repository ships synthetic exports for a fictional coffee shop:

```bash
gsc-insights quick-wins examples/period_b
gsc-insights declining examples/period_a examples/period_b
gsc-insights movers examples/period_a examples/period_b --kind losers
gsc-insights cannibalisation examples/period_b
gsc-insights branded examples/period_b --brand "bright\s*leaf"
gsc-insights breakdown examples/period_b --by countries --limit 5
gsc-insights report examples/period_b --compare examples/period_a \
    --config examples/config.yml --out gsc-report
```

For comparison commands, the first export is **period A (earlier)** and the second is
**period B (later)**.

Every command accepts `-f table|csv|json`, `-o FILE` and `--limit N` (`0` for no limit).

```bash
gsc-insights quick-wins export.zip -f csv -o quick-wins.csv
```

`quick-wins`, `declining` and `movers` also accept `--min-impressions N` to raise or lower the
impression threshold for a single run without editing your config file (it overrides
`min_impressions` from the config).

```bash
gsc-insights quick-wins export.zip --min-impressions 500
```

## How the analyses work

**Quick wins.** A row qualifies when its average position is between `min_position` and
`max_position`, it has at least `min_impressions`, and its CTR is below
`expected_ctr(position) * ctr_gap_ratio`. The expected CTR comes from a position-to-CTR curve that
is linearly interpolated between the points you define. `extra_clicks` is
`impressions * expected_ctr - clicks`: the clicks you would gain from a better title and snippet
without moving up. Tune the curve with your own data, since CTR varies by industry and SERP features.

**Declining.** Both periods are joined on the query (or page). A row is reported when it had at
least `min_impressions` in period A and lost at least `min_click_drop` clicks and `min_pct_drop`
percent. Rows that disappeared entirely are included with status `lost`.
`position_delta` is positive when the ranking got worse.

**Cannibalisation.** Within the query + page table, queries with `min_pages` or more pages
(each with at least `min_page_impressions`) are listed. URLs are normalised (query string,
fragment, trailing slash and host case are ignored) unless you disable `normalize_urls`.
Severity depends on how much impression share the strongest page holds.

**Branded split.** Patterns in `brand.patterns` are case-insensitive regular expressions
combined with OR.

## Configuration

Generate a commented starting point and edit it:

```bash
gsc-insights init-config -o gsc-insights.yml
gsc-insights quick-wins export/ -c gsc-insights.yml
```

```yaml
brand:
  patterns: ["acme", "a\\s*c\\s*m\\s*e"]
ctr_curve: {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.075, 10: 0.02, 20: 0.0045}
quick_wins:
  min_impressions: 100
  ctr_gap_ratio: 0.8
declining:
  min_click_drop: 5
  min_pct_drop: 20
```

Unknown keys are rejected so typos do not pass silently. See `examples/config.yml` for every option.

## Report output

`gsc-insights report` writes `index.html` (self-contained, no external assets, values are
HTML-escaped) and a `csv/` folder with one file per result set, for example
`quick_wins_queries.csv`, `cannibalisation.csv`, `declining_queries.csv`, `movers_queries_gainers.csv`.
Sections that need data you did not provide (for example query + page data or a second period)
are left out.

## Project layout

```
src/gsc_insights/
  loader.py        read folders, ZIPs and CSVs into tables
  config.py        YAML config, CTR curve
  analysis/        quick_wins, compare (declining), movers, cannibalisation, branded, breakdown
  insights.py      run every analysis
  report.py        HTML + CSV report
  cli.py           command line interface
scripts/generate_examples.py   rebuilds the synthetic example data
```

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md). All example data is synthetic.

## License

MIT, see [LICENSE](LICENSE).

## Run with Docker

A multi-arch image (amd64, arm64) is published to GitHub Container Registry on every change to `main`, so you can run the tool without installing Python:

```bash
docker run --rm -v "$PWD:/work" ghcr.io/saizul/gsc-insights:latest --help
```

Mount the folder that holds your input files (and where reports should be written) at `/work`.
