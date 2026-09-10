"""Orchestrate YAML loading, rules, and repository coverage analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import Coverage, Finding, Report
from .rules import UpdateSpec, validate_config
from .scanner import Manifest, manifest_directory, path_pattern_matches, scan_repository


class ConfigError(Exception):
    """An input/configuration file could not be read or decoded."""

    def __init__(self, message: str, code: str = "CONFIG_READ") -> None:
        super().__init__(message)
        self.code = code


def load_yaml(path: Path) -> Any:
    """Read YAML with the safe loader and convert parser failures to one error."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0] if str(exc) else "invalid YAML"
        raise ConfigError(f"cannot parse {path}: {detail}", "CONFIG_YAML") from exc


def _display_config(config_path: Path, repo_root: Path) -> str:
    try:
        return config_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return config_path.as_posix()


def _manifest_matches(spec: UpdateSpec, manifest: Manifest) -> bool:
    if spec.ecosystem not in manifest.ecosystems:
        return False
    directory = manifest_directory(manifest.path)
    return any(path_pattern_matches(pattern, directory) for pattern in spec.directories)


def _apply_coverage(report: Report, repo_root: Path, specs: list[UpdateSpec]) -> None:
    manifests = scan_repository(repo_root)
    report.coverage = Coverage(
        enabled=True,
        update_entries=len(specs),
        recognized_manifests=len(manifests),
    )
    covered_by: dict[str, list[str]] = {manifest.path: [] for manifest in manifests}

    for spec in specs:
        matched = [manifest for manifest in manifests if _manifest_matches(spec, manifest)]
        for manifest in matched:
            covered_by[manifest.path].append(spec.path)
        report.coverage.matches.append(
            {
                "update": spec.path,
                "ecosystem": spec.ecosystem,
                "directories": list(spec.directories),
                "files": [manifest.path for manifest in matched],
            }
        )
        if not matched:
            for directory_index, directory in enumerate(spec.directories):
                directory_path = (
                    f"{spec.path}.directory"
                    if len(spec.directories) == 1
                    else f"{spec.path}.directories[{directory_index}]"
                )
                report.findings.append(
                    Finding(
                        "COVERAGE_NO_MANIFEST",
                        "warning",
                        directory_path,
                        f"{spec.ecosystem} directory {directory} matches no recognized dependency manifest",
                        "check the path or add --no-coverage when this is intentional",
                    )
                )

    for manifest in manifests:
        if covered_by[manifest.path]:
            continue
        report.coverage.unmanaged_manifests.append(manifest.path)
        ecosystems = ", ".join(manifest.ecosystems)
        report.findings.append(
            Finding(
                "COVERAGE_UNMANAGED",
                "warning",
                manifest.path,
                f"recognized {ecosystems} manifest is not covered by any update entry",
                "add an update entry for this directory or document why it is excluded",
            )
        )

    report.coverage.covered_manifests = sum(bool(paths) for paths in covered_by.values())


def check_repository(
    config_path: Path,
    repo_root: Path,
    *,
    coverage: bool = True,
) -> Report:
    """Return a report for one repository/configuration pair."""

    config_path = config_path.resolve()
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise ConfigError(f"repository path is not a directory: {repo_root}", "REPO_READ")
    data = load_yaml(config_path)
    report = Report(_display_config(config_path, repo_root))
    specs = validate_config(data, report)
    if coverage:
        _apply_coverage(report, repo_root, specs)
    else:
        report.coverage = Coverage(enabled=False, update_entries=len(specs))
    return report
