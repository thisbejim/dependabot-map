"""Conservative, offline repository manifest discovery and path matching."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path, PurePosixPath

from .model import Manifest

# These are the ecosystem names used by Dependabot plus a few spellings seen in
# older examples. Aliases are normalised before validation and matching.
ECOSYSTEM_ALIASES: dict[str, str] = {
    "docker_compose": "docker-compose",
    "go-modules": "gomod",
    "gitsubmodule": "gitsubmodule",
    "npm_and_yarn": "npm",
    "python": "pip",
    "submodules": "gitsubmodule",
}

KNOWN_ECOSYSTEMS = frozenset(
    {
        "bazel",
        "bun",
        "bundler",
        "cargo",
        "composer",
        "conda",
        "deno",
        "devcontainers",
        "docker",
        "docker-compose",
        "dotnet-sdk",
        "elm",
        "github-actions",
        "gomod",
        "gradle",
        "helm",
        "julia",
        "maven",
        "mix",
        "nix",
        "npm",
        "nuget",
        "opentofu",
        "pip",
        "pre-commit",
        "pub",
        "rust-toolchain",
        "sbt",
        "swift",
        "gitsubmodule",
        "terraform",
        "uv",
        "vcpkg",
    }
)

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "coverage",
        "target",
        ".gradle",
    }
)


def canonical_ecosystem(value: str) -> str:
    """Return a stable ecosystem spelling for comparisons and output."""

    lowered = value.strip().lower()
    return ECOSYSTEM_ALIASES.get(lowered, lowered)


def _posix_relative(path: Path, root: Path) -> str:
    return PurePosixPath(path.relative_to(root)).as_posix()


def _manifest_candidates(
    path: str, names_in_directory: set[str]
) -> tuple[tuple[str, ...], str] | None:
    """Return ecosystems and a human label for a recognized relative path."""

    pure = PurePosixPath(path)
    name = pure.name
    lower = name.lower()
    parts = pure.parts

    if (
        len(parts) >= 3
        and parts[-3:-1] == (".github", "workflows")
        and lower.endswith((".yml", ".yaml"))
    ):
        return ("github-actions",), "github-actions-workflow"
    if len(parts) == 1 and lower in {"action.yml", "action.yaml"}:
        return ("github-actions",), "github-actions-action"

    if name in {"MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel"}:
        return ("bazel",), "bazel-manifest"
    if name in {"Gemfile", "Gemfile.lock"}:
        return ("bundler",), "bundler-manifest"
    if name in {"Cargo.toml", "Cargo.lock"}:
        return ("cargo",), "cargo-manifest"
    if name in {"composer.json", "composer.lock"}:
        return ("composer",), "composer-manifest"
    if name in {"environment.yml", "environment.yaml", "conda.yml", "conda.yaml"}:
        return ("conda",), "conda-manifest"
    if lower in {"devcontainer.json", "devcontainer.jsonc"} and (
        ".devcontainer" in parts or len(parts) == 1
    ):
        return ("devcontainers",), "devcontainer-manifest"
    if lower == "dockerfile" or lower.startswith("dockerfile.") or lower.endswith(".dockerfile"):
        return ("docker",), "dockerfile"
    if lower in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        return ("docker-compose",), "compose-manifest"
    if name == "elm.json":
        return ("elm",), "elm-manifest"
    if name in {"go.mod", "go.sum"}:
        return ("gomod",), "go-manifest"
    if lower in {
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "gradle.lockfile",
    }:
        return ("gradle",), "gradle-manifest"
    if name == "Chart.yaml":
        return ("helm",), "helm-chart"
    if name in {"Project.toml", "Manifest.toml"}:
        return ("julia",), "julia-manifest"
    if name == "pom.xml":
        return ("maven",), "maven-manifest"
    if name in {"mix.exs", "mix.lock"}:
        return ("mix",), "mix-manifest"
    if name in {
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    }:
        return ("npm",), "javascript-manifest"
    if name == "bun.lock":
        return ("bun",), "bun-lockfile"
    if name in {"deno.json", "deno.jsonc"}:
        return ("deno",), "deno-manifest"
    if name == "flake.lock":
        return ("nix",), "nix-lockfile"
    if name == "global.json":
        return ("dotnet-sdk",), "dotnet-sdk-manifest"
    if lower.endswith((".csproj", ".fsproj", ".vbproj")) or lower in {
        "packages.config",
        "packages.lock.json",
    }:
        return ("nuget",), "nuget-manifest"
    if lower.startswith("requirements") and lower.endswith((".txt", ".in")):
        return ("pip",), "pip-requirements"
    if name in {"setup.py", "setup.cfg", "Pipfile", "Pipfile.lock"}:
        return ("pip",), "python-manifest"
    if name == "pyproject.toml":
        ecosystems = ["pip"]
        if "uv.lock" in names_in_directory:
            ecosystems.append("uv")
        return tuple(ecosystems), "python-project"
    if name == "uv.lock":
        return ("uv",), "uv-lockfile"
    if name in {"pubspec.yaml", "pubspec.lock"}:
        return ("pub",), "pub-manifest"
    if name == "Package.swift":
        return ("swift",), "swift-manifest"
    if name in {"rust-toolchain", "rust-toolchain.toml"}:
        return ("rust-toolchain",), "rust-toolchain-manifest"
    if name == "build.sbt":
        return ("sbt",), "sbt-manifest"
    if name == "vcpkg.json":
        return ("vcpkg",), "vcpkg-manifest"
    if name == ".gitmodules":
        return ("gitsubmodule",), "git-submodules"
    if name in {".pre-commit-config.yaml", ".pre-commit-config.yml"}:
        return ("pre-commit",), "pre-commit-config"
    if lower.endswith((".tf", ".tofu")):
        return ("opentofu", "terraform"), "terraform-file"
    if name in {".terraform.lock.hcl", "terragrunt.hcl"}:
        return ("opentofu",), "opentofu-lockfile"

    return None


def scan_repository(root: Path) -> list[Manifest]:
    """Discover recognizable dependency manifests below *root*.

    The walk is deterministic, does not follow directory symlinks, and prunes
    generated/cache directories to avoid noisy false positives.
    """

    root = root.resolve()
    directory_names: dict[str, set[str]] = {}
    files: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRECTORIES)
        current = Path(dirpath)
        relative_directory = "" if current == root else _posix_relative(current, root)
        directory_names[relative_directory] = set(filenames)
        for filename in sorted(filenames):
            candidate = current / filename
            if candidate.is_symlink():
                continue
            files.append((candidate, _posix_relative(candidate, root)))

    manifests: list[Manifest] = []
    for _candidate, relative in sorted(files, key=lambda item: item[1]):
        parent = PurePosixPath(relative).parent.as_posix()
        names = directory_names.get("" if parent == "." else parent, set())
        result = _manifest_candidates(relative, names)
        if result is None:
            continue
        ecosystems, kind = result
        manifests.append(Manifest(relative, tuple(sorted(set(ecosystems))), kind))
    return manifests


def _segment_matches(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value, pattern)


def path_pattern_matches(pattern: str, path: str) -> bool:
    """Match a Dependabot directory pattern against a repo-relative directory.

    `*` matches one path segment and `**` matches zero or more segments. A
    root pattern (`/`) matches every directory.
    """

    pattern_parts = [part for part in pattern.strip("/").split("/") if part]
    path_parts = [part for part in path.strip("/").split("/") if part]
    if not pattern_parts:
        return True

    def match(pattern_index: int, path_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        part = pattern_parts[pattern_index]
        if part == "**":
            return match(pattern_index + 1, path_index) or (
                path_index < len(path_parts) and match(pattern_index, path_index + 1)
            )
        return (
            path_index < len(path_parts)
            and _segment_matches(part, path_parts[path_index])
            and match(pattern_index + 1, path_index + 1)
        )

    return match(0, 0)


def manifest_directory(manifest_path: str) -> str:
    """Return the normalized Dependabot directory for a manifest path."""

    parent = PurePosixPath(manifest_path).parent.as_posix()
    return "/" if parent == "." else f"/{parent}"
