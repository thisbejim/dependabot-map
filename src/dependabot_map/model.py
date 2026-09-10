"""Small, serialisable data structures shared by the checker and renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True, slots=True)
class Finding:
    """A deterministic, actionable diagnostic."""

    code: str
    severity: str
    path: str
    message: str
    fix: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown finding severity: {self.severity}")

    def as_dict(self) -> dict[str, str]:
        result = {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }
        if self.fix:
            result["fix"] = self.fix
        return result


@dataclass(frozen=True, slots=True)
class Manifest:
    """A file that can be associated with one or more Dependabot ecosystems."""

    path: str
    ecosystems: tuple[str, ...]
    kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "ecosystems": list(self.ecosystems),
            "kind": self.kind,
        }


@dataclass(slots=True)
class Coverage:
    """Repository coverage details included in reports."""

    enabled: bool = True
    update_entries: int = 0
    recognized_manifests: int = 0
    covered_manifests: int = 0
    unmanaged_manifests: list[str] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "update_entries": self.update_entries,
            "recognized_manifests": self.recognized_manifests,
            "covered_manifests": self.covered_manifests,
            "unmanaged_manifests": sorted(self.unmanaged_manifests),
            "matches": sorted(
                self.matches,
                key=lambda item: (item.get("update", ""), item.get("ecosystem", "")),
            ),
        }


@dataclass(slots=True)
class Report:
    """The complete result of one check."""

    config: str
    findings: list[Finding] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    schema_version: int = 1

    def ordered_findings(self) -> list[Finding]:
        rank = {"error": 0, "warning": 1, "info": 2}
        return sorted(
            self.findings,
            key=lambda item: (rank[item.severity], item.path, item.code, item.message),
        )

    def counts(self) -> dict[str, int]:
        return {
            severity: sum(item.severity == severity for item in self.findings)
            for severity in SEVERITIES
        }

    def is_valid(self, strict: bool = False) -> bool:
        counts = self.counts()
        return counts["error"] == 0 and (not strict or counts["warning"] == 0)

    def as_dict(self, strict: bool = False) -> dict[str, Any]:
        counts = self.counts()
        return {
            "schema_version": self.schema_version,
            "valid": self.is_valid(strict),
            "summary": counts,
            "config": self.config,
            "findings": [finding.as_dict() for finding in self.ordered_findings()],
            "coverage": self.coverage.as_dict(),
        }
