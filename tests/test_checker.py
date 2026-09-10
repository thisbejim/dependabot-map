from __future__ import annotations

import json
from pathlib import Path

import pytest

from dependabot_map.checker import ConfigError, check_repository
from dependabot_map.output import render_json, render_sarif, render_text


def write_config(repo: Path, text: str) -> Path:
    path = repo / ".github" / "dependabot.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_config_covers_npm_and_actions(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"requests": "1"}}', encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
""",
    )

    report = check_repository(config, tmp_path)

    assert report.is_valid()
    assert report.counts() == {"error": 0, "warning": 0, "info": 0}
    assert report.coverage.covered_manifests == 2
    assert report.coverage.unmanaged_manifests == []


def test_coverage_flags_stale_entry_and_unmanaged_manifest(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /frontend-old
    schedule:
      interval: weekly
""",
    )

    report = check_repository(config, tmp_path)
    codes = {finding.code for finding in report.findings}

    assert {"COVERAGE_NO_MANIFEST", "COVERAGE_UNMANAGED"} <= codes
    assert sorted(report.coverage.unmanaged_manifests) == ["package.json", "requirements.txt"]
    assert report.is_valid()
    assert not report.is_valid(strict=True)


def test_no_coverage_suppresses_repository_findings(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    config = write_config(
        tmp_path,
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /missing
    schedule:
      interval: weekly
""",
    )

    report = check_repository(config, tmp_path, coverage=False)

    assert report.coverage.enabled is False
    assert not any(finding.code.startswith("COVERAGE_") for finding in report.findings)


def test_semantic_errors_include_actionable_paths(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """version: 1
registries:
  private:
    type: npm-registry
updates:
  - package-ecosystem: made-up
    directory: src
    directories: [/src]
    schedule:
      interval: fortnightly
      time: 27:90
    registries: [missing]
    multi-ecosystem-group: absent
""",
    )

    report = check_repository(config, tmp_path)
    finding_map = {(finding.code, finding.path) for finding in report.findings}

    assert ("CONFIG_VERSION", "version") in finding_map
    assert ("ECOSYSTEM_UNKNOWN", "updates[0].package-ecosystem") in finding_map
    assert ("DIRECTORY_CONFLICT", "updates[0]") in finding_map
    assert ("DIRECTORY_NOT_ROOTED", "updates[0].directory") in finding_map
    assert ("SCHEDULE_INTERVAL", "updates[0].schedule.interval") in finding_map
    assert ("REGISTRY_UNDEFINED", "updates[0].registries[0]") in finding_map
    assert ("GROUP_UNDEFINED", "updates[0].multi-ecosystem-group") in finding_map


def test_duplicate_directories_are_errors(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /packages
    schedule: {interval: weekly}
  - package-ecosystem: npm
    directory: /packages/app
    schedule: {interval: weekly}
""",
    )

    report = check_repository(config, tmp_path, coverage=False)

    overlaps = [finding for finding in report.findings if finding.code == "DIRECTORY_OVERLAP"]
    assert overlaps
    assert overlaps[0].severity == "error"


def test_registry_and_multi_group_references_can_be_valid(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """version: 2
registries:
  private:
    type: npm-registry
    url: https://registry.example.test
multi-ecosystem-groups:
  all:
    schedule: {interval: monthly}
updates:
  - package-ecosystem: npm
    directory: /
    schedule: {interval: weekly}
    registries: [private]
    multi-ecosystem-group: all
""",
    )

    report = check_repository(config, tmp_path, coverage=False)

    assert not any(finding.severity == "error" for finding in report.findings)


def test_malformed_yaml_is_an_input_error(tmp_path: Path) -> None:
    config = write_config(tmp_path, "version: [2\n")

    with pytest.raises(ConfigError, match="cannot parse") as error:
        check_repository(config, tmp_path)

    assert error.value.code == "CONFIG_YAML"


def test_renderers_are_machine_readable(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule: {interval: weekly}
""",
    )
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    report = check_repository(config, tmp_path)

    payload = json.loads(render_json(report))
    sarif = json.loads(render_sarif(report))
    text = render_text(report)

    assert payload["schema_version"] == 1
    assert payload["valid"] is True
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"] == []
    assert text.startswith("PASS dependabot-map\n")
