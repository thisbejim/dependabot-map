from __future__ import annotations

from pathlib import Path

from dependabot_map.scanner import manifest_directory, path_pattern_matches, scan_repository


def test_directory_patterns_use_segments() -> None:
    assert path_pattern_matches("/", "/anything/deeper")
    assert path_pattern_matches("/packages/*", "/packages/app")
    assert not path_pattern_matches("/packages/*", "/packages/app/src")
    assert path_pattern_matches("/packages/**", "/packages/app/src")
    assert path_pattern_matches("/packages/**", "/packages")
    assert not path_pattern_matches("/services/*", "/packages/app")


def test_manifest_directory_is_rooted() -> None:
    assert manifest_directory("package.json") == "/"
    assert manifest_directory("packages/api/package.json") == "/packages/api"


def test_scanner_discovers_common_manifests_and_prunes_caches(tmp_path: Path) -> None:
    files = [
        "MODULE.bazel",
        "Gemfile",
        "Cargo.toml",
        "composer.json",
        "Dockerfile",
        "go.mod",
        "pom.xml",
        "package.json",
        "bun.lock",
        "deno.json",
        "global.json",
        "flake.lock",
        "Project.toml",
        "requirements-dev.txt",
        "pyproject.toml",
        "uv.lock",
        "pubspec.yaml",
        "Package.swift",
        "rust-toolchain.toml",
        "build.sbt",
        "vcpkg.json",
        ".gitmodules",
        ".pre-commit-config.yaml",
        "main.tf",
        ".github/workflows/ci.yaml",
        ".devcontainer/devcontainer.json",
        ".devcontainer/README.md",
        ".terraform.lock.hcl",
        "terragrunt.hcl",
        "module.tofu",
    ]
    for relative in files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    ignored = tmp_path / "node_modules" / "nested" / "package.json"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("", encoding="utf-8")

    manifests = scan_repository(tmp_path)
    by_path = {manifest.path: manifest for manifest in manifests}

    assert "node_modules/nested/package.json" not in by_path
    assert by_path["pyproject.toml"].ecosystems == ("pip", "uv")
    assert by_path["main.tf"].ecosystems == ("opentofu", "terraform")
    assert by_path[".gitmodules"].ecosystems == ("gitsubmodule",)
    assert by_path["bun.lock"].ecosystems == ("bun",)
    assert by_path[".github/workflows/ci.yaml"].ecosystems == ("github-actions",)
    assert len(manifests) == len(files) - 1
