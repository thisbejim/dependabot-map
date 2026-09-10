from __future__ import annotations

import json
from pathlib import Path

from dependabot_map.cli import main


def test_cli_defaults_to_discovered_config_and_supports_json(tmp_path: Path, capsys) -> None:
    config = tmp_path / ".github" / "dependabot.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule: {interval: weekly}
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    code = main(["check", "--repo", str(tmp_path), "--format", "json"])
    captured = capsys.readouterr()

    assert code == 0
    assert json.loads(captured.out)["valid"] is True
    assert captured.err == ""


def test_cli_strict_promotes_coverage_warning(tmp_path: Path, capsys) -> None:
    config = tmp_path / ".github" / "dependabot.yml"
    config.parent.mkdir(parents=True)
    config.write_text(
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /old
    schedule: {interval: weekly}
""",
        encoding="utf-8",
    )

    code = main(["check", str(config), "--repo", str(tmp_path), "--strict"])
    captured = capsys.readouterr()

    assert code == 1
    assert "COVERAGE_NO_MANIFEST" in captured.out


def test_cli_missing_config_returns_usage_error(tmp_path: Path, capsys) -> None:
    code = main(["check", "--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 2
    assert "CONFIG_MISSING" in captured.err
