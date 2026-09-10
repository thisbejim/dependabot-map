"""Human, JSON, and SARIF report renderers."""

from __future__ import annotations

import json
from typing import Any

from .model import Finding, Report


def render_json(report: Report, *, strict: bool = False) -> str:
    return json.dumps(report.as_dict(strict), indent=2, sort_keys=True) + "\n"


def _sarif_level(finding: Finding) -> str:
    return {"error": "error", "warning": "warning", "info": "note"}[finding.severity]


def render_sarif(report: Report) -> str:
    findings = report.ordered_findings()
    rule_ids = sorted({finding.code for finding in findings})
    rules = [
        {
            "id": rule_id,
            "shortDescription": {"text": rule_id.replace("_", " ").lower()},
        }
        for rule_id in rule_ids
    ]
    results: list[dict[str, Any]] = []
    for finding in findings:
        result: dict[str, Any] = {
            "ruleId": finding.code,
            "level": _sarif_level(finding),
            "message": {"text": f"{finding.path}: {finding.message}"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": report.config},
                    },
                    "logicalLocations": [{"fullyQualifiedName": finding.path}],
                }
            ],
        }
        if finding.fix:
            result["fixes"] = [{"description": {"text": finding.fix}}]
        results.append(result)
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "dependabot-map",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/thisbejim/dependabot-map",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_text(report: Report, *, strict: bool = False) -> str:
    status = "PASS" if report.is_valid(strict) else "FAIL"
    lines = [f"{status} dependabot-map", f"Config: {report.config}"]
    coverage = report.coverage
    if coverage.enabled:
        lines.append(
            "Coverage: "
            f"{coverage.update_entries} update entries, "
            f"{coverage.covered_manifests}/{coverage.recognized_manifests} recognized manifests covered"
        )
    else:
        lines.append("Coverage: disabled")
    counts = report.counts()
    lines.append(
        f"Summary: {counts['error']} errors, {counts['warning']} warnings, {counts['info']} info"
    )
    for finding in report.ordered_findings():
        line = f"{finding.severity.upper()} {finding.code} {finding.path}: {finding.message}"
        if finding.fix:
            line += f" (fix: {finding.fix})"
        lines.append(line)
    return "\n".join(lines) + "\n"
