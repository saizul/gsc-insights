# Contributing

Thanks for taking the time to improve gsc-insights.

## Development setup

```bash
git clone https://github.com/saizul/gsc-insights.git
cd gsc-insights
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

```bash
ruff check .
ruff format --check .
pytest
```

CI runs the same commands on Python 3.10 to 3.13. Please run them before opening a pull request.

## Guidelines

- Keep runtime dependencies minimal (currently `jinja2`, `rich`, `pyyaml`). Prefer the standard library.
- Add tests for every behaviour change. Tests must use the synthetic data in `examples/`
  or small inline CSV strings, never real client data.
- Analysis functions stay pure: they take tables and config and return dataclasses. Output
  formatting belongs in `output.py` and `report.py`.
- If you change the example data, edit `scripts/generate_examples.py` and re-run it
  rather than editing the CSV files by hand.
- Update `CHANGELOG.md` under an "Unreleased" heading.

## Reporting bugs

Please include the command you ran, the header row of the CSV file that failed (not the data),
your Python version and the full error message.
