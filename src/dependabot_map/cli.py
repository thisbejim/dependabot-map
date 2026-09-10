"""Command-line entry point for dependabot-map."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checker import ConfigError, check_repository
from .output import render_json, render_sarif, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dependabot-map",
        description="Check Dependabot configuration and map entries to local manifests.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser(
        "check", help="validate a Dependabot config and inspect repository coverage"
    )
    check.add_argument(
        "config", nargs="?", help="config path (defaults to .github/dependabot.yml or .yaml)"
    )
    check.add_argument(
        "--repo", default=".", help="repository root to scan (default: current directory)"
    )
    check.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    check.add_argument("--strict", action="store_true", help="treat coverage warnings as failures")
    check.add_argument(
        "--no-coverage", action="store_true", help="skip repository manifest coverage checks"
    )
    return parser


def _resolve_config(argument: str | None, repo: Path) -> Path:
    if argument:
        return Path(argument).expanduser().resolve()
    for candidate in (repo / ".github" / "dependabot.yml", repo / ".github" / "dependabot.yaml"):
        if candidate.is_file():
            return candidate.resolve()
    raise ConfigError(
        "no config found; expected .github/dependabot.yml or .github/dependabot.yaml",
        "CONFIG_MISSING",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "check":
        parser.error("a command is required")
    repo = Path(args.repo).expanduser().resolve()
    try:
        config = _resolve_config(args.config, repo)
        report = check_repository(config, repo, coverage=not args.no_coverage)
    except ConfigError as exc:
        print(f"ERROR {exc.code}: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        sys.stdout.write(render_json(report, strict=args.strict))
    elif args.format == "sarif":
        sys.stdout.write(render_sarif(report))
    else:
        sys.stdout.write(render_text(report, strict=args.strict))
    return 0 if report.is_valid(args.strict) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
