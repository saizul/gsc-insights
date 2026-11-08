# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
