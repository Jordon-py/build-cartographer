"""Heuristic impact-analysis service for safe code edits.

Given a target file/symbol and a repo map, this module estimates dependencies,
likely affected areas, risk level, and practical verification suggestions.
"""

from __future__ import annotations

import re
from pathlib import Path

from cartographer.config import DEFAULT_EXCLUDE_PATTERNS
from cartographer.models import ImpactReport, RepoMap
from cartographer.resources import is_text_like, read_text_file

PYTHON_IMPORT_RE = re.compile(r"^\s*(?:from\s+([a-zA-Z0-9_\.]+)\s+import|import\s+([a-zA-Z0-9_\. ,]+))", re.MULTILINE)
JS_IMPORT_RE = re.compile(r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\))""")


def _resolve_repo_map(repo_map: RepoMap | dict) -> RepoMap:
    # Accept either a validated repo map or plain JSON-shaped tool data.
    if isinstance(repo_map, RepoMap):
        return repo_map
    return RepoMap.model_validate(repo_map)


def _resolve_target(root: Path, target: str, files: list[str]) -> Path | None:
    # Try absolute, repo-relative, and same-filename resolution in that order.
    direct_path = Path(target)
    if direct_path.is_absolute() and direct_path.exists():
        return direct_path

    relative_path = root / target
    if relative_path.exists():
        return relative_path

    target_name = direct_path.name or target
    for file_name in files:
        if Path(file_name).name == target_name:
            return root / file_name
    return None


def _extract_imports(file_path: Path | None) -> list[str]:
    # Parse a small subset of Python and JS/TS import syntax for cheap heuristics.
    if file_path is None:
        return []

    text = read_text_file(file_path)
    if not text:
        return []

    imports: list[str] = []
    if file_path.suffix == ".py":
        for left, right in PYTHON_IMPORT_RE.findall(text):
            if left:
                imports.append(left)
            if right:
                imports.extend(part.strip() for part in right.split(",") if part.strip())
    elif file_path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
        for left, right in JS_IMPORT_RE.findall(text):
            if left:
                imports.append(left)
            if right:
                imports.append(right)

    seen: set[str] = set()
    return [item for item in imports if not (item in seen or seen.add(item))]


def _find_imported_by(root: Path, target_path: Path | None, files: list[str], target: str) -> list[str]:
    # Search for lightweight reference terms instead of doing full static analysis.
    reference_terms = {target}
    if target_path is not None:
        reference_terms.update(
            {
                target_path.stem,
                target_path.name,
                ".".join(target_path.with_suffix("").relative_to(root).parts),
            }
        )

    imported_by: list[str] = []
    for file_name in files:
        candidate = root / file_name
        if target_path is not None and candidate == target_path:
            continue
        if not is_text_like(candidate):
            continue
        if any(part in candidate.parts for part in DEFAULT_EXCLUDE_PATTERNS):
            continue

        text = read_text_file(candidate)
        if text and any(term and term in text for term in reference_terms):
            imported_by.append(file_name)
    return imported_by


def _infer_layer(target_path: Path | None, target: str) -> str:
    # Use path segments as a simple proxy for architectural layers.
    parts = [part.lower() for part in (target_path.parts if target_path else Path(target).parts)]

    if any(part in {"api", "routes", "router", "views", "controllers"} for part in parts):
        return "API / routing"
    if any(part in {"models", "model", "schemas", "schema", "entities", "database", "db"} for part in parts):
        return "Data / domain"
    if any(part in {"components", "pages", "ui", "frontend", "client"} for part in parts):
        return "Frontend"
    if any(part in {"services", "lib", "utils"} for part in parts):
        return "Service / business logic"
    if any(part in {"config"} for part in parts):
        return "Configuration"
    if any("test" in part for part in parts):
        return "Tests"
    return "Application"


def estimate_change_impact(target: str, repo_map: RepoMap | dict) -> ImpactReport:
    # Assemble a best-effort impact report that is cheap enough to run often.
    resolved_map = _resolve_repo_map(repo_map)
    root = resolved_map.root_path
    target_path = _resolve_target(root, target, resolved_map.files)
    imports = _extract_imports(target_path)
    imported_by = _find_imported_by(root, target_path, resolved_map.files, target)

    if target_path:
        relative_target = target_path.relative_to(root).as_posix()
        folders = [
            parent.as_posix()
            for parent in reversed(target_path.relative_to(root).parents)
            if parent.as_posix() != "."
        ]
    else:
        relative_target = target
        folders = []

    layer = _infer_layer(target_path, target)
    affected_paths = [relative_target] if relative_target else []
    affected_paths.extend(imported_by[:10])
    concerns: list[str] = []

    if layer in {"Configuration", "API / routing", "Data / domain"}:
        concerns.append(f"{layer} changes can ripple into multiple features.")
    if len(imported_by) > 5:
        concerns.append("The target is referenced by several files and may require broader regression testing.")
    if target_path is None:
        concerns.append("The target could not be resolved to a concrete file, so the analysis is heuristic.")

    risk_score = len(imported_by)
    if layer in {"Configuration", "API / routing", "Data / domain"}:
        risk_score += 2
    if relative_target in resolved_map.entrypoints or relative_target in resolved_map.config_files:
        risk_score += 2

    if risk_score >= 7:
        risk_level = "high"
    elif risk_score >= 3:
        risk_level = "medium"
    else:
        risk_level = "low"

    return ImpactReport(
        target=relative_target,
        summary=(
            f"Changing {relative_target} most likely affects the {layer} layer. "
            f"It imports {len(imports)} modules and appears to be referenced by {len(imported_by)} files."
        ),
        layer=layer,
        risk_level=risk_level,
        imports=imports,
        imported_by=imported_by,
        folders=folders,
        affected_paths=affected_paths,
        concerns=concerns,
        test_recommendations=[
            "Run the closest unit or integration tests for the affected layer.",
            "Verify the main user flow or entrypoint after making the change.",
        ],
    )
