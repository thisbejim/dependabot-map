# Contributing

Thanks for helping make Dependabot configuration safer to review.

* Keep the core checker offline, read-only, and deterministic.
* Add or update a fixture under `tests/fixtures/` for behavior changes.
* Run `uv run pytest`, `uv run ruff check .`, and `uv build` before opening a
  pull request.
* Do not add telemetry, credential collection, or a network dependency to the
  checking path.

New ecosystem support should include the manifest mapping, documentation, and
coverage tests. If Dependabot behavior is uncertain, prefer a conservative
“unknown” result over an assertion that a file is covered.
