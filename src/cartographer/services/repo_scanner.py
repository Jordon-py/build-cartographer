"""Repository scanning service that builds Cartographer's structural map.

The scanner walks a repository once and extracts file categories, likely
entrypoints, config/env/routes/schema hints, technologies, and recent changes.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from cartographer.config import (
    CONFIG_FILE_NAMES,
    ENTRYPOINT_FILE_NAMES,
    ROUTE_HINTS,
    SCHEMA_HINTS,
)
from cartographer.models import RepoMap, RepoScanRequest
from cartographer.resources import read_readme, read_text_file

LOWERCASE_CONFIG_FILE_NAMES = {name.lower() for name in CONFIG_FILE_NAMES}
LOWERCASE_ENTRYPOINT_FILE_NAMES = {name.lower() for name in ENTRYPOINT_FILE_NAMES}


def _matches_include(relative_path: Path, include_patterns: list[str]) -> bool:
    # Only apply include filtering when the caller asked for it.
    if not include_patterns:
        return True
    relative_text = relative_path.as_posix()
    return any(relative_path.match(pattern) or relative_text.endswith(pattern) for pattern in include_patterns)


def _should_skip(relative_path: Path, exclude_patterns: list[str], max_depth: int | None) -> bool:
    # Stop processing paths that are too deep or explicitly excluded.
    if max_depth is not None and len(relative_path.parts) > max_depth:
        return True

    relative_text = relative_path.as_posix()
    return any(
        pattern in relative_path.parts
        or relative_path.match(pattern)
        or relative_text.startswith(pattern)
        for pattern in exclude_patterns
    )


def _normalize_extension(path: Path) -> str:
    # Group files by suffix while keeping extensionless files visible in the map.
    return path.suffix.lower() or "[no extension]"


def _is_route_file(path: Path) -> bool:
    # Route hints give the intent layer a quick sense of how requests flow through the app.
    return any(hint in path.as_posix().lower() for hint in ROUTE_HINTS)


def _is_schema_file(path: Path) -> bool:
    # Model and schema files usually capture the domain language of the project.
    return any(hint in path.as_posix().lower() for hint in SCHEMA_HINTS)


def _is_config_file(path: Path) -> bool:
    # Config files explain runtime wiring, dependencies, and deployment assumptions.
    lowered = path.name.lower()
    return lowered in LOWERCASE_CONFIG_FILE_NAMES or ".config." in lowered


def _is_entrypoint(path: Path) -> bool:
    # Entrypoint names are a fast heuristic for where the app starts up.
    return path.name.lower() in LOWERCASE_ENTRYPOINT_FILE_NAMES


def _detect_project_name(root: Path) -> str:
    # Prefer explicit package metadata over guessing from the folder name.
    package_json = root / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data.get("name"), str) and data["name"].strip():
            return data["name"].strip()

    pyproject_text = read_text_file(root / "pyproject.toml", max_chars=10000)
    if pyproject_text:
        match = re.search(r'^\s*name\s*=\s*"([^"]+)"', pyproject_text, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()

    return root.name


def _detect_technologies(files: list[str], sample_texts: list[str]) -> list[str]:
    # Keep stack detection intentionally lightweight so scans stay fast and predictable.
    text_blob = "\n".join(sample_texts).lower()
    lowered_files = [file_name.lower() for file_name in files]
    technologies: list[str] = []

    def add(name: str, condition: bool) -> None:
        # Preserve insertion order so the reported stack reads naturally.
        if condition and name not in technologies:
            technologies.append(name)

    add("Python", any(name.endswith(".py") for name in lowered_files))
    add("JavaScript", any(name.endswith((".js", ".jsx")) for name in lowered_files))
    add("TypeScript", any(name.endswith((".ts", ".tsx")) for name in lowered_files))
    add("React", "react" in text_blob or any(name.endswith((".jsx", ".tsx")) for name in lowered_files))
    add("FastAPI", "fastapi" in text_blob)
    add("Flask", "flask" in text_blob)
    add("Django", "django" in text_blob)
    add("Next.js", "next" in text_blob or any("next.config" in name for name in lowered_files))
    add("Pydantic", "pydantic" in text_blob)
    return technologies


def _recent_files(root: Path, file_paths: list[Path], limit: int = 10) -> list[str]:
    # Surface the most recently touched files so review and resume flows stay grounded.
    ranked = sorted(file_paths, key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.relative_to(root).as_posix() for path in ranked[:limit]]


def scan_repo(request: RepoScanRequest | str | Path) -> RepoMap:
    # Walk the repo once and collect the signals the rest of Cartographer depends on.
    if not isinstance(request, RepoScanRequest):
        request = RepoScanRequest(repo_path=request)

    root = request.repo_path
    directories: list[str] = []
    files: list[str] = []
    entrypoints: list[str] = []
    config_files: list[str] = []
    env_files: list[str] = []
    route_files: list[str] = []
    schema_files: list[str] = []
    file_types: Counter[str] = Counter()
    warnings: list[str] = []
    file_paths: list[Path] = []

    for path in root.rglob("*"):
        # Evaluate everything relative to the repo root so the map is portable.
        relative_path = path.relative_to(root)
        if _should_skip(relative_path, request.exclude_patterns, request.max_depth):
            continue
        if not _matches_include(relative_path, request.include_patterns):
            continue

        relative_text = relative_path.as_posix()
        if path.is_dir():
            directories.append(relative_text)
            continue

        files.append(relative_text)
        file_paths.append(path)
        file_types[_normalize_extension(path)] += 1

        if _is_entrypoint(path):
            entrypoints.append(relative_text)
        if _is_config_file(path):
            config_files.append(relative_text)
        if path.name.startswith(".env"):
            env_files.append(relative_text)
        if _is_route_file(path):
            route_files.append(relative_text)
        if _is_schema_file(path):
            schema_files.append(relative_text)

    # Read just a few high-signal files so stack inference stays cheap.
    sample_texts = [read_readme(root) or ""]
    for candidate in config_files[:5]:
        text = read_text_file(root / candidate, max_chars=10000)
        if text:
            sample_texts.append(text)

    technologies = _detect_technologies(files, sample_texts)
    project_name = _detect_project_name(root)
    recent_files = _recent_files(root, file_paths) if file_paths else []

    if not files:
        warnings.append("No files were discovered during the scan.")

    summary = (
        f"{project_name} contains {len(files)} files across {len(directories)} directories. "
        f"Detected technologies: {', '.join(technologies) if technologies else 'unknown'}."
    )

    return RepoMap(
        root_path=root,
        project_name=project_name,
        summary=summary,
        directories=sorted(directories),
        files=sorted(files),
        file_types=dict(sorted(file_types.items())),
        entrypoints=sorted(entrypoints),
        config_files=sorted(config_files),
        env_files=sorted(env_files),
        route_files=sorted(route_files),
        schema_files=sorted(schema_files),
        recent_files=recent_files,
        technologies=technologies,
        warnings=warnings,
    )
