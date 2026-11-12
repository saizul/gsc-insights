# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `--min-impressions N` option for `quick-wins`, `declining` and `movers`, overriding
  the `min_impressions` value from the config for a single run.
- `anomalies` command: flags days whose clicks, impressions, CTR or position break
  sharply from the trailing baseline, using a robust z-score (median absolute
  deviation) plus a minimum percentage change. The default `weekday` baseline
  learns day-of-week factors so normal weekend dips are not reported; `rolling`
  uses a plain median. Missing dates count as zero traffic and are marked.
  Configurable through a new `anomalies` config section and `--metric`,
  `--baseline`, `--window`, `--threshold` and `--min-pct-change` flags.
- `report` includes a "Daily anomalies" section and `csv/anomalies.csv` when the
  export has daily data.
- The synthetic period B example data now contains a one-day dip on 2026-10-21.

## [0.1.0] - 2026-11-08

### Added
- Loader for Search Console Performance exports: folder of CSV files, the ZIP
  downloaded from the UI, or a single CSV (including API-style files with
  `query` and `page` columns). Files are recognised by header, not file name.
- `quick-wins`: positions 4-20 with high impressions and CTR below a configurable
  position-to-CTR curve, with an estimate of extra clicks.
- `declining`: queries or pages that lost clicks between two exports.
- `movers`: gainers, losers, new, lost and position movers.
- `cannibalisation`: queries answered by several pages, with severity and advice.
- `branded`: branded vs non-branded split using regular expressions.
- `breakdown`: device and country share of clicks and impressions.
- `report`: single-file HTML report plus one CSV per result set.
- YAML configuration and `init-config` command.
- Synthetic example exports in `examples/`.
