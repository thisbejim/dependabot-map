# dependabot-map

Offline Dependabot configuration and repository coverage doctor.

`dependabot-map` answers two questions before a pull request lands:

1. Is `.github/dependabot.yml` shaped and cross-referenced correctly?
2. Which dependency manifests in this checkout does each update entry cover?

It is read-only and makes no network requests. It does not run Dependabot or
resolve private registry credentials; it is a fast local ruleset and coverage
map that complements schema hooks such as `check-jsonschema`.

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install dependabot-map
```

Or with pipx:

```bash
pipx install dependabot-map
```

From a checkout while developing:

```bash
uv run --extra dev dependabot-map check --repo .
```

## Use

```bash
# Discover .github/dependabot.yml (or .yaml) in the current repository.
dependabot-map check

# Check a different checkout/config and fail on coverage warnings.
dependabot-map check .github/dependabot.yml --repo ../service --strict

# Produce CI-friendly reports.
dependabot-map check --format json > dependabot-map.json
dependabot-map check --format sarif > dependabot-map.sarif
```

Exit status is `0` for a clean report, `1` when findings remain (or warnings
are promoted by `--strict`), and `2` for bad command input or unreadable/
malformed YAML. Use `--no-coverage` when the repository intentionally keeps a
manifest outside the local heuristic table.

Example:

```text
FAIL dependabot-map
Config: .github/dependabot.yml
Coverage: 2 update entries, 1/2 recognized manifests covered
Summary: 0 errors, 1 warnings, 0 info
WARNING COVERAGE_NO_MANIFEST updates[1].directory: npm directory /frontend-old matches no recognized dependency manifest (fix: check the path or add --no-coverage when this is intentional)
```

## What is checked

The checker validates Dependabot v2, update entry types, ecosystem names,
directory/directory-glob conflicts, schedules, registry references, groups,
common option shapes, and deterministic path normalization. Coverage scans
common manifests for Bazel, Bun, Bundler, Cargo, Composer, Conda, Deno, Dev
Containers, Docker, Docker Compose, .NET SDK, Elm, GitHub Actions, Go modules,
Gradle, Helm, Julia, Maven, Mix, Nix, npm/Yarn, NuGet, OpenTofu, pip,
pre-commit, Pub, Rust toolchains, sbt, Swift, Git submodules, Terraform, uv,
and vcpkg. A file can belong to more than one ecosystem (for example a
`pyproject.toml` with `uv.lock`). The accepted ecosystem names follow [GitHub's
supported ecosystem reference](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories).

The scanner reports “recognized” files, not a proof that a repository has no
other dependency sources. See [`docs/product-spec.md`](docs/product-spec.md)
for the full contract and [`docs/research.md`](docs/research.md) for the
opportunity evidence and competing tools.

## CI

The repository's own workflow runs tests and Ruff on Python 3.11–3.13. A
consumer can add a lightweight check such as:

```yaml
- name: Check Dependabot coverage
  run: dependabot-map check --format sarif > dependabot-map.sarif
```

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv build
```

Contributions should keep checks offline, deterministic, and free of telemetry.
Please include a fixture and a focused test when adding an ecosystem or rule.

## License

MIT. See [`LICENSE`](LICENSE).
