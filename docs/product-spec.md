# dependabot-map product specification

Status: approved for implementation
Date: 2026-09-10

## Problem

Dependabot configuration is easy to make syntactically valid while still
pointing at the wrong directories, stale manifests, or unsupported references.
GitHub then discovers the problem only after the file is pushed and a scheduled
job runs. Existing schema validators answer “is this YAML shaped correctly?”;
they do not answer “what in this checkout will this entry actually cover?”

## Product

`dependabot-map` is an offline command-line doctor for
`.github/dependabot.yml`. It validates the configuration rules that can be
checked locally and builds a conservative map from each update entry to the
dependency manifests discovered in the repository.

The tool is intentionally read-only. It never contacts GitHub, package
registries, or a hosted service, and it never prints registry credentials.

## Primary workflow

```text
dependabot-map check [CONFIG] [--repo REPOSITORY]
```

If `CONFIG` is omitted, the tool looks for `.github/dependabot.yml`, then
`.github/dependabot.yaml`, in the repository supplied by `--repo` (the current
directory by default).

The command emits human-readable findings by default. `--format json` is a
stable machine-readable report and `--format sarif` is suitable for code
scanning annotations. `--strict` promotes coverage warnings to failures;
`--no-coverage` runs only configuration checks.

Exit codes:

* `0`: no errors (and no warnings when `--strict` is used).
* `1`: one or more findings make the report non-clean.
* `2`: invalid command usage, missing files, or unreadable/malformed YAML.

## Checks

### Configuration checks

* YAML must decode to a mapping; `version: 2` and a non-empty `updates` list
  are required.
* Each update entry must be a mapping with a known `package-ecosystem` and a
  string `directory` or non-empty `directories` list (not both).
* Directory paths are normalized to repository-relative POSIX paths. Duplicate
  or overlapping entries for the same ecosystem and target branch are
  reported.
* `schedule` is checked for a supported interval and valid optional day, time,
  timezone, or cron expression shape.
* Registry references must resolve to a top-level `registries` mapping; registry
  definitions must have a type and URL when the ecosystem requires them.
* `groups` and `multi-ecosystem-groups` references must resolve to update
  entries, and their schedule blocks must be mappings.
* Unsupported or misspelled option names are reported with a useful path and
  correction hint where the local rules are unambiguous.

The checker is a practical local ruleset, not a promise to model every private
Dependabot updater behavior. Unknown keys that are valid extension points are
not rejected without evidence.

### Repository coverage checks

The scanner walks the repository without following symlinks and ignores VCS,
virtual-environment, dependency-cache, build, and generated directories. It
recognizes common manifest filenames for the supported Dependabot ecosystems.
For each update entry it reports:

* `COVERAGE_NO_MANIFEST` when its directory or glob matches no recognizable
  manifest (likely stale or mistyped configuration).
* `COVERAGE_UNMANAGED` when a recognizable manifest is not covered by any
  update entry for its ecosystem.
* A coverage summary showing entries, manifests, covered manifests, and
  intentionally unknown files.

Coverage is deliberately conservative: the report says “recognized” rather
than claiming that an arbitrary repository has no dependencies. GitHub Actions
uses the special Dependabot convention that `directory: "/"` covers workflow
files and a root `action.yml`/`action.yaml`.

## Output contract

The JSON report has `schema_version: 1`, `valid`, `summary`, `findings`, and
`coverage` keys. Every finding includes `code`, `severity`, `path`, `message`,
and an optional `fix`. SARIF uses version 2.1.0 with each finding's code as the
rule id. Ordering is deterministic (path, code, message) so reports are easy
to diff in CI.

## Non-goals

* Running Dependabot, Docker, package managers, or a network service.
* Proving that every dependency file is understood by GitHub.
* Resolving credentials, private registries, or repository permissions.
* Automatically editing the user's configuration.

## Acceptance criteria

1. A new user can install the package with `uv tool install` or `pipx` and run
   the default command in an existing repository.
2. A valid fixture produces a clean report in text, JSON, and SARIF formats.
3. Fixtures cover malformed YAML, schema errors, semantic conflicts, registry
   and group references, missing manifests, unmanaged manifests, globs, and
   GitHub Actions root coverage.
4. CI runs the test suite and linter on supported Python versions without
   network access.
5. The repository contains a concise README, MIT license, contributing notes,
   and a reproducible release build.
