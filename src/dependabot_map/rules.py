"""Local Dependabot configuration rules and normalized update entries."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from .model import Finding, Report
from .scanner import KNOWN_ECOSYSTEMS, canonical_ecosystem

INTERVALS = frozenset({"daily", "weekly", "monthly", "quarterly", "semiannually", "yearly", "cron"})
WEEKDAYS = frozenset({"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"})
VERSIONING_STRATEGIES = frozenset({"auto", "widen", "increase", "increase-if-necessary"})

SUPPORTED_UPDATE_KEYS = frozenset(
    {
        "package-ecosystem",
        "directory",
        "directories",
        "schedule",
        "open-pull-requests-limit",
        "versioning-strategy",
        "target-branch",
        "labels",
        "assignees",
        "reviewers",
        "milestone",
        "commit-message",
        "ignore",
        "allow",
        "groups",
        "registries",
        "rebase-strategy",
        "cooldown",
        "pull-request-branch-name",
        "vendor",
        "insecure-external-code-execution",
        "multi-ecosystem-group",
        "exclude-paths",
    }
)


@dataclass(frozen=True, slots=True)
class UpdateSpec:
    """The subset of an update entry needed for repository coverage."""

    index: int
    ecosystem: str
    directories: tuple[str, ...]
    target_branch: str

    @property
    def path(self) -> str:
        return f"updates[{self.index}]"


def _finding(
    report: Report,
    code: str,
    severity: str,
    path: str,
    message: str,
    fix: str | None = None,
) -> None:
    report.findings.append(Finding(code, severity, path, message, fix))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_directory(value: str) -> tuple[str | None, str | None]:
    """Normalize a Dependabot directory while reporting one shape problem."""

    raw = value.strip().replace("\\", "/")
    if not raw:
        return None, "empty"
    rooted = raw.startswith("/")
    if not rooted:
        raw = f"/{raw}"
    pieces: list[str] = []
    for piece in raw.split("/"):
        if piece in {"", "."}:
            continue
        if piece == "..":
            if not pieces:
                return None, "escape"
            pieces.pop()
            continue
        pieces.append(piece)
    normalized = "/" if not pieces else "/" + "/".join(pieces)
    return normalized, None if rooted else "not-rooted"


def _literal_prefix(pattern: str) -> str:
    pieces = []
    for piece in pattern.strip("/").split("/"):
        if not piece or any(char in piece for char in "*?["):
            break
        pieces.append(piece)
    return "/" if not pieces else "/" + "/".join(pieces)


def patterns_may_overlap(first: str, second: str) -> bool:
    """Conservatively identify duplicate or obviously overlapping directories."""

    if first == second or first == "/" or second == "/":
        return True
    first_prefix = _literal_prefix(first)
    second_prefix = _literal_prefix(second)
    return (
        first_prefix == second_prefix
        or first_prefix.startswith(second_prefix.rstrip("/") + "/")
        or second_prefix.startswith(first_prefix.rstrip("/") + "/")
    )


def _validate_schedule(report: Report, schedule: Any, path: str) -> None:
    if schedule is None:
        _finding(
            report,
            "SCHEDULE_REQUIRED",
            "error",
            path,
            "each update entry needs a schedule mapping",
            "add schedule: {interval: weekly}",
        )
        return
    if not isinstance(schedule, dict):
        _finding(report, "SCHEDULE_SHAPE", "error", path, "schedule must be a mapping")
        return

    interval = schedule.get("interval")
    if not isinstance(interval, str) or interval.lower() not in INTERVALS:
        _finding(
            report,
            "SCHEDULE_INTERVAL",
            "error",
            f"{path}.interval",
            "interval must be one of daily, weekly, monthly, quarterly, semiannually, yearly, or cron",
        )
    else:
        interval = interval.lower()
    day = schedule.get("day")
    if day is not None:
        valid_day = isinstance(day, str) and (day.lower() in WEEKDAYS or day.isdigit())
        if isinstance(day, int) and not isinstance(day, bool):
            valid_day = 1 <= day <= 31
        if not valid_day:
            _finding(
                report,
                "SCHEDULE_DAY",
                "error",
                f"{path}.day",
                "day must be a weekday name or a day number from 1 to 31",
            )
    time_value = schedule.get("time")
    if time_value is not None:
        valid_time = isinstance(time_value, str) and bool(
            re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value)
        )
        if not valid_time:
            _finding(
                report,
                "SCHEDULE_TIME",
                "error",
                f"{path}.time",
                "time must use 24-hour HH:MM format",
            )
    timezone = schedule.get("timezone")
    if timezone is not None and (not isinstance(timezone, str) or not timezone.strip()):
        _finding(
            report,
            "SCHEDULE_TIMEZONE",
            "error",
            f"{path}.timezone",
            "timezone must be a non-empty string",
        )
    cronjob = schedule.get("cronjob")
    if interval == "cron" and not isinstance(cronjob, str):
        _finding(
            report,
            "SCHEDULE_CRONJOB",
            "error",
            f"{path}.cronjob",
            "cron interval requires a cronjob string",
        )
    elif cronjob is not None:
        if not isinstance(cronjob, str) or len(cronjob.split()) != 5:
            _finding(
                report,
                "SCHEDULE_CRONJOB",
                "error",
                f"{path}.cronjob",
                "cronjob must contain five fields",
            )


def _validate_string_list(report: Report, value: Any, path: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        _finding(report, "OPTION_LIST", "error", path, "value must be a non-empty list of strings")


def _validate_registries(
    report: Report, entry: dict[str, Any], path: str, registry_names: set[str]
) -> None:
    if "registries" not in entry:
        return
    value = entry["registries"]
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        _finding(
            report,
            "REGISTRY_REFS",
            "error",
            f"{path}.registries",
            "registries must be a name, '*', or a list of names",
        )
        return
    for index, name in enumerate(values):
        if name != "*" and name not in registry_names:
            _finding(
                report,
                "REGISTRY_UNDEFINED",
                "error",
                f"{path}.registries[{index}]",
                f"registry '{name}' is not defined in top-level registries",
                "define it under registries or use '*'",
            )


def _validate_groups(
    report: Report, entry: dict[str, Any], path: str, multi_groups: set[str]
) -> None:
    groups = entry.get("groups")
    if groups is not None:
        if not isinstance(groups, dict):
            _finding(report, "GROUPS_SHAPE", "error", f"{path}.groups", "groups must be a mapping")
        else:
            for name, definition in groups.items():
                group_path = f"{path}.groups.{name}"
                if not isinstance(definition, dict):
                    _finding(
                        report,
                        "GROUP_SHAPE",
                        "error",
                        group_path,
                        "group definition must be a mapping",
                    )
                    continue
                if "patterns" in definition:
                    _validate_string_list(report, definition["patterns"], f"{group_path}.patterns")
                if "update-types" in definition:
                    _validate_string_list(
                        report, definition["update-types"], f"{group_path}.update-types"
                    )
    if "multi-ecosystem-group" in entry:
        value = entry["multi-ecosystem-group"]
        if not isinstance(value, str) or value not in multi_groups:
            _finding(
                report,
                "GROUP_UNDEFINED",
                "error",
                f"{path}.multi-ecosystem-group",
                "multi-ecosystem-group must name a top-level multi-ecosystem-groups entry",
            )


def _validate_registries_top_level(report: Report, value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, dict):
        _finding(report, "REGISTRIES_SHAPE", "error", "registries", "registries must be a mapping")
        return set()
    names: set[str] = set()
    for name, definition in value.items():
        path = f"registries.{name}"
        if not isinstance(name, str) or not name.strip():
            _finding(
                report, "REGISTRY_NAME", "error", path, "registry names must be non-empty strings"
            )
            continue
        names.add(name)
        if not isinstance(definition, dict):
            _finding(
                report, "REGISTRY_CONFIG", "error", path, "registry definition must be a mapping"
            )
            continue
        if not isinstance(definition.get("type"), str) or not definition["type"].strip():
            _finding(
                report, "REGISTRY_TYPE", "error", f"{path}.type", "registry definition needs a type"
            )
        if "url" not in definition:
            _finding(
                report,
                "REGISTRY_URL",
                "warning",
                path,
                "registry has no URL; private registry resolution may fail",
            )
        elif not isinstance(definition["url"], str) or not definition["url"].strip():
            _finding(
                report,
                "REGISTRY_URL",
                "error",
                f"{path}.url",
                "registry URL must be a non-empty string",
            )
    return names


def _validate_multi_groups(report: Report, value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, dict):
        _finding(
            report,
            "MULTI_GROUPS_SHAPE",
            "error",
            "multi-ecosystem-groups",
            "value must be a mapping",
        )
        return set()
    names: set[str] = set()
    for name, definition in value.items():
        path = f"multi-ecosystem-groups.{name}"
        if not isinstance(name, str) or not name.strip():
            _finding(report, "GROUP_NAME", "error", path, "group names must be non-empty strings")
            continue
        names.add(name)
        if not isinstance(definition, dict):
            _finding(
                report, "MULTI_GROUP_SHAPE", "error", path, "group definition must be a mapping"
            )
            continue
        if "schedule" not in definition:
            _finding(
                report,
                "GROUP_SCHEDULE",
                "error",
                path,
                "multi-ecosystem group needs a schedule mapping",
            )
        else:
            _validate_schedule(report, definition["schedule"], f"{path}.schedule")
    return names


def validate_config(data: Any, report: Report) -> list[UpdateSpec]:
    """Validate decoded YAML and return update entries usable by coverage."""

    if not isinstance(data, dict):
        _finding(report, "CONFIG_NOT_MAPPING", "error", "$", "configuration must be a YAML mapping")
        return []

    version = data.get("version")
    if version != 2:
        _finding(report, "CONFIG_VERSION", "error", "version", "configuration must set version: 2")

    updates = data.get("updates")
    if not isinstance(updates, list) or not updates:
        _finding(report, "UPDATES_REQUIRED", "error", "updates", "updates must be a non-empty list")
        updates = []

    registry_names = _validate_registries_top_level(report, data.get("registries"))
    multi_groups = _validate_multi_groups(report, data.get("multi-ecosystem-groups"))
    specs: list[UpdateSpec] = []

    for index, entry in enumerate(updates):
        path = f"updates[{index}]"
        if not isinstance(entry, dict):
            _finding(report, "UPDATE_SHAPE", "error", path, "update entry must be a mapping")
            continue
        for key in entry:
            if key not in SUPPORTED_UPDATE_KEYS:
                hint = difflib.get_close_matches(str(key), SUPPORTED_UPDATE_KEYS, n=1, cutoff=0.78)
                fix = f"did you mean '{hint[0]}'?" if hint else None
                _finding(
                    report,
                    "OPTION_UNKNOWN",
                    "warning",
                    f"{path}.{key}",
                    "option is not recognized by dependabot-map",
                    fix,
                )

        ecosystem_value = entry.get("package-ecosystem")
        ecosystem: str | None = None
        if not isinstance(ecosystem_value, str) or not ecosystem_value.strip():
            _finding(
                report,
                "ECOSYSTEM_REQUIRED",
                "error",
                f"{path}.package-ecosystem",
                "package-ecosystem must be a string",
            )
        else:
            ecosystem = canonical_ecosystem(ecosystem_value)
            if ecosystem not in KNOWN_ECOSYSTEMS:
                _finding(
                    report,
                    "ECOSYSTEM_UNKNOWN",
                    "error",
                    f"{path}.package-ecosystem",
                    f"unsupported package ecosystem '{ecosystem_value}'",
                    "use a documented Dependabot ecosystem name",
                )

        has_directory = "directory" in entry
        has_directories = "directories" in entry
        if has_directory and has_directories:
            _finding(
                report,
                "DIRECTORY_CONFLICT",
                "error",
                path,
                "set directory or directories, not both",
            )
        if not has_directory and not has_directories:
            _finding(
                report,
                "DIRECTORY_REQUIRED",
                "error",
                path,
                "update entry needs directory or directories",
            )

        raw_directories: list[Any]
        directory_paths: list[str] = []
        if has_directories and not has_directory:
            raw_directories = entry["directories"] if isinstance(entry["directories"], list) else []
            if not isinstance(entry["directories"], list) or not raw_directories:
                _finding(
                    report,
                    "DIRECTORIES_SHAPE",
                    "error",
                    f"{path}.directories",
                    "directories must be a non-empty list",
                )
        elif has_directory and not has_directories:
            raw_directories = [entry["directory"]]
        else:
            # Report the explicit directory's shape even when both spellings
            # were supplied; the conflict finding should not hide a typo.
            raw_directories = [entry["directory"]]

        for directory_index, raw_directory in enumerate(raw_directories):
            directory_path = (
                f"{path}.directory" if has_directory else f"{path}.directories[{directory_index}]"
            )
            if not isinstance(raw_directory, str):
                _finding(
                    report, "DIRECTORY_SHAPE", "error", directory_path, "directory must be a string"
                )
                continue
            normalized, issue = normalize_directory(raw_directory)
            if normalized is None:
                code = "DIRECTORY_ESCAPE" if issue == "escape" else "DIRECTORY_SHAPE"
                _finding(
                    report,
                    code,
                    "error",
                    directory_path,
                    "directory cannot escape the repository root",
                )
                continue
            if issue == "empty":
                _finding(
                    report, "DIRECTORY_SHAPE", "error", directory_path, "directory cannot be empty"
                )
            elif issue == "not-rooted":
                _finding(
                    report,
                    "DIRECTORY_NOT_ROOTED",
                    "error",
                    directory_path,
                    "Dependabot directories must start with '/'; normalized path is " + normalized,
                    f"write '{normalized}'",
                )
            directory_paths.append(normalized)

        _validate_schedule(report, entry.get("schedule"), f"{path}.schedule")

        if "versioning-strategy" in entry:
            value = entry["versioning-strategy"]
            if not isinstance(value, str) or value not in VERSIONING_STRATEGIES:
                _finding(
                    report,
                    "VERSIONING_STRATEGY",
                    "error",
                    f"{path}.versioning-strategy",
                    "unsupported versioning strategy",
                )
        if "open-pull-requests-limit" in entry:
            value = entry["open-pull-requests-limit"]
            if not _is_int(value) or value < 0:
                _finding(
                    report,
                    "PR_LIMIT",
                    "error",
                    f"{path}.open-pull-requests-limit",
                    "limit must be a non-negative integer",
                )
        for option in ("labels", "assignees", "reviewers", "exclude-paths"):
            if option in entry:
                _validate_string_list(report, entry[option], f"{path}.{option}")
        if "cooldown" in entry:
            cooldown = entry["cooldown"]
            if not isinstance(cooldown, dict):
                _finding(
                    report,
                    "COOLDOWN_SHAPE",
                    "error",
                    f"{path}.cooldown",
                    "cooldown must be a mapping",
                )
            else:
                for key, value in cooldown.items():
                    if not str(key).endswith("-days") or not _is_int(value) or value < 0:
                        _finding(
                            report,
                            "COOLDOWN_VALUE",
                            "error",
                            f"{path}.cooldown.{key}",
                            "cooldown day values must be non-negative integers",
                        )

        _validate_registries(report, entry, path, registry_names)
        _validate_groups(report, entry, path, multi_groups)

        if ecosystem is not None and ecosystem in KNOWN_ECOSYSTEMS and directory_paths:
            target_branch = entry.get("target-branch", "main")
            if not isinstance(target_branch, str) or not target_branch.strip():
                _finding(
                    report,
                    "TARGET_BRANCH",
                    "error",
                    f"{path}.target-branch",
                    "target-branch must be a non-empty string",
                )
                target_branch = "main"
            specs.append(UpdateSpec(index, ecosystem, tuple(directory_paths), target_branch))

    for left_index, left in enumerate(specs):
        for right in specs[left_index + 1 :]:
            if left.ecosystem != right.ecosystem or left.target_branch != right.target_branch:
                continue
            for left_directory in left.directories:
                for right_directory in right.directories:
                    if patterns_may_overlap(left_directory, right_directory):
                        _finding(
                            report,
                            "DIRECTORY_OVERLAP",
                            "error",
                            f"updates[{right.index}]",
                            "directory "
                            f"{right_directory} overlaps updates[{left.index}] "
                            f"directory {left_directory} for {left.ecosystem}",
                            "merge the entries or make their directories disjoint",
                        )

    for spec in specs:
        for left_index, first in enumerate(spec.directories):
            for second in spec.directories[left_index + 1 :]:
                if patterns_may_overlap(first, second):
                    _finding(
                        report,
                        "DIRECTORY_OVERLAP",
                        "error",
                        spec.path,
                        f"directories {first} and {second} overlap for {spec.ecosystem}",
                        "remove the duplicate or overlapping directory",
                    )
    return specs
