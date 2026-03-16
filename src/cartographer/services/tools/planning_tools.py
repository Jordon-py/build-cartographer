"""MCP planning tools built on top of scan, intent, impact, and state memory.

This module provides user-facing tools for repo summaries, change-impact views,
next-step guidance, and developer resume context.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from cartographer.models import IntentSummary, NextStepSuggestion, ProjectState, RepoMap, RepoScanRequest
from cartographer.resources import read_readme
from cartographer.services.impact_analyzer import estimate_change_impact
from cartographer.services.intent_ledger import summarize_intent as build_intent_summary
from cartographer.services.repo_scanner import scan_repo as build_repo_map
from cartographer.state import StateManager


def _resolve_repo_path(repo_path: str | None, state_manager: StateManager) -> Path:
    # Prefer the explicit repo path, then fall back to the repo remembered in state.
    if repo_path:
        return Path(repo_path).expanduser().resolve(strict=False)

    state = state_manager.load()
    if state.repo_path is not None:
        return state.repo_path

    raise ValueError("A repo_path is required until the project has been scanned at least once.")


def _ensure_repo_map(repo_path: str | None, state_manager: StateManager) -> RepoMap:
    # Reuse the cached repo map when possible and rescan only when needed.
    state = state_manager.load()
    resolved_path = _resolve_repo_path(repo_path, state_manager)

    if state.repo_map is not None and state.repo_map.root_path == resolved_path:
        return state.repo_map

    request = RepoScanRequest(repo_path=resolved_path)
    repo_map = build_repo_map(request)
    state_manager.record_scan(repo_map, request=request)
    return repo_map


def _ensure_intent_summary(repo_path: str | None, state_manager: StateManager) -> IntentSummary:
    # Build intent on demand so repo summary and resume flows stay high signal.
    repo_map = _ensure_repo_map(repo_path, state_manager)
    state = state_manager.load()
    if state.intent_summary is not None and state.repo_path == repo_map.root_path:
        return state.intent_summary

    intent_summary = build_intent_summary(repo_map, readme_text=read_readme(repo_map.root_path))
    state_manager.record_intent(intent_summary)
    return intent_summary


def _describe_change(file_path: str, repo_map: RepoMap) -> str:
    # Explain why a recent file matters using the scanner's structural categories.
    reasons: list[str] = []
    if file_path in repo_map.entrypoints:
        reasons.append("entrypoint")
    if file_path in repo_map.route_files:
        reasons.append("routing")
    if file_path in repo_map.schema_files:
        reasons.append("domain model")
    if file_path in repo_map.config_files or file_path in repo_map.env_files:
        reasons.append("configuration")
    if not reasons:
        reasons.append("application code")
    return ", ".join(reasons)


def _summarize_recent_changes(repo_map: RepoMap, recent_files: list[str]) -> list[dict[str, str]]:
    # Turn raw recent file paths into review-friendly change callouts.
    return [
        {"path": file_path, "reason": _describe_change(file_path, repo_map)}
        for file_path in recent_files[:5]
    ]


def _build_repo_summary_payload(repo_map: RepoMap, intent_summary: IntentSummary, state: ProjectState) -> dict:
    # Combine scan facts, inferred intent, and recent changes into one fast context view.
    recent_files = state.recent_files_changed or repo_map.recent_files
    recent_changes = _summarize_recent_changes(repo_map, recent_files)
    return {
        "project_name": repo_map.project_name,
        "repo_path": str(repo_map.root_path),
        "summary": repo_map.summary,
        "latest_inferred_intent": intent_summary.summary,
        "technologies": repo_map.technologies,
        "entrypoints": repo_map.entrypoints,
        "config_files": repo_map.config_files,
        "route_files": repo_map.route_files,
        "schema_files": repo_map.schema_files,
        "recent_changes_that_matter": recent_changes,
        "review_focus": recent_changes,
    }


def _build_next_steps(state_manager: StateManager) -> list[NextStepSuggestion]:
    # Suggest concrete next actions from the current repo state instead of generic advice.
    state = state_manager.load()
    suggestions: list[NextStepSuggestion] = []

    if state.repo_map is None:
        suggestions.append(
            NextStepSuggestion(
                step="Run scan_repo",
                reason="Cartographer needs a fresh mental map before it can reason about the project.",
                priority="high",
            )
        )
        return suggestions

    if state.last_worked_on_feature or state.last_worked_on_files:
        suggestions.append(
            NextStepSuggestion(
                step=f"Resume work on {state.last_worked_on_feature or 'the last task'}",
                reason=state.mental_model or "This is the most recent developer context stored in project memory.",
                priority="high",
                target_paths=state.last_worked_on_files[:5],
            )
        )

    if state.intent_summary is None:
        suggestions.append(
            NextStepSuggestion(
                step="Run summarize_intent",
                reason="Turning the repo map into a project summary adds usable reasoning context.",
                priority="high",
                target_paths=state.repo_map.entrypoints[:3] or state.repo_map.files[:3],
            )
        )

    if state.open_questions:
        suggestions.append(
            NextStepSuggestion(
                step="Answer the open questions",
                reason="Clarifying unknowns will improve future planning and impact guesses.",
                priority="high",
                target_paths=state.repo_map.entrypoints[:3],
            )
        )

    if state.repo_map.entrypoints:
        suggestions.append(
            NextStepSuggestion(
                step="Inspect the main entrypoints",
                reason="Entry files reveal how the project starts up and how the layers connect.",
                priority="medium",
                target_paths=state.repo_map.entrypoints[:3],
            )
        )

    if state.repo_map.schema_files:
        suggestions.append(
            NextStepSuggestion(
                step="Review the schema and model files",
                reason="These files usually reveal the core domain and data flow.",
                priority="medium",
                target_paths=state.repo_map.schema_files[:3],
            )
        )

    if state.impact_report is not None and state.impact_report.risk_level in {"high", "critical"}:
        suggestions.append(
            NextStepSuggestion(
                step="Run targeted regression checks",
                reason="The latest impact analysis suggests the change touches a sensitive area.",
                priority="high",
                target_paths=state.impact_report.affected_paths[:5],
            )
        )

    if state.repo_map.env_files or state.repo_map.config_files:
        suggestions.append(
            NextStepSuggestion(
                step="Verify environment and configuration assumptions",
                reason="Config files often explain how the project is wired together.",
                priority="low",
                target_paths=(state.repo_map.env_files + state.repo_map.config_files)[:5],
            )
        )

    if not suggestions:
        suggestions.append(
            NextStepSuggestion(
                step="Pick a target file and run impact_view",
                reason="Impact analysis is the next best step once the repo has been mapped.",
                priority="medium",
            )
        )

    return suggestions


def run_repo_summary(repo_path: str | None = None, state_manager: StateManager | None = None) -> dict:
    # Return the fastest useful project overview for regaining context.
    manager = state_manager or StateManager()
    repo_map = _ensure_repo_map(repo_path, manager)
    intent_summary = _ensure_intent_summary(repo_path, manager)
    return _build_repo_summary_payload(repo_map, intent_summary, manager.load())


def run_summarize_intent(repo_path: str | None = None, state_manager: StateManager | None = None) -> dict:
    # Expose intent inference as a tool and persist the result for later planning.
    manager = state_manager or StateManager()
    intent_summary = _ensure_intent_summary(repo_path, manager)
    project_state = manager.load()
    return {
        "intent_summary": intent_summary.model_dump(mode="json"),
        "project_state": project_state.model_dump(mode="json"),
    }


def run_impact_view(target: str, repo_path: str | None = None, state_manager: StateManager | None = None) -> dict:
    # Produce a heuristic blast-radius view for a file or symbol.
    manager = state_manager or StateManager()
    repo_map = _ensure_repo_map(repo_path, manager)
    impact_report = estimate_change_impact(target, repo_map)
    project_state = manager.record_impact(impact_report)
    return {
        "impact_report": impact_report.model_dump(mode="json"),
        "project_state": project_state.model_dump(mode="json"),
    }


def run_suggest_next_steps(repo_path: str | None = None, state_manager: StateManager | None = None) -> dict:
    # Keep suggestions grounded in the latest repo map, intent, impact, and remembered work.
    manager = state_manager or StateManager()
    if repo_path:
        _ensure_repo_map(repo_path, manager)

    next_steps = _build_next_steps(manager)
    project_state = manager.record_next_steps(next_steps)
    return {
        "next_steps": [step.model_dump(mode="json") for step in next_steps],
        "project_state": project_state.model_dump(mode="json"),
    }


def run_remember_work(
    *,
    feature: str | None = None,
    files: list[str] | None = None,
    mental_model: str | None = None,
    notes: list[str] | None = None,
    repo_path: str | None = None,
    state_manager: StateManager | None = None,
) -> dict:
    # Persist the developer's current working set so the next session can resume quickly.
    manager = state_manager or StateManager()
    if repo_path:
        manager.remember_repo(repo_path)
    project_state = manager.remember_work(
        feature=feature,
        files=files,
        mental_model=mental_model,
        notes=notes,
    )
    return {"project_state": project_state.model_dump(mode="json")}


def run_resume_context(repo_path: str | None = None, state_manager: StateManager | None = None) -> dict:
    # Combine stored working memory with repo structure so a developer can re-enter flow fast.
    manager = state_manager or StateManager()
    state = manager.load()
    if repo_path or state.repo_map is not None:
        try:
            repo_map = _ensure_repo_map(repo_path, manager)
            intent_summary = _ensure_intent_summary(repo_path, manager)
            repo_summary = _build_repo_summary_payload(repo_map, intent_summary, manager.load())
        except ValueError:
            repo_summary = {}
    else:
        repo_summary = {}

    return {
        "resume_context": manager.resume_context(),
        "repo_summary": repo_summary,
    }


def register_planning_tools(mcp: FastMCP, state_manager: StateManager | None = None) -> None:
    # Register the higher-level reasoning tools that sit on top of scan and state memory.
    manager = state_manager or StateManager()

    @mcp.tool
    def repo_summary(repo_path: str | None = None) -> dict:
        """Return a quick repo summary grounded in the current project state."""

        return run_repo_summary(repo_path=repo_path, state_manager=manager)

    @mcp.tool
    def summarize_intent(repo_path: str | None = None) -> dict:
        """Summarize what the project appears to be."""

        return run_summarize_intent(repo_path=repo_path, state_manager=manager)

    @mcp.tool
    def impact_view(target: str, repo_path: str | None = None) -> dict:
        """Estimate which areas of the repository may be affected by a change."""

        return run_impact_view(target=target, repo_path=repo_path, state_manager=manager)

    @mcp.tool
    def suggest_next_steps(repo_path: str | None = None) -> dict:
        """Suggest the next useful actions for understanding or editing the project."""

        return run_suggest_next_steps(repo_path=repo_path, state_manager=manager)

    @mcp.tool
    def remember_work(
        feature: str | None = None,
        files: list[str] | None = None,
        mental_model: str | None = None,
        notes: list[str] | None = None,
        repo_path: str | None = None,
    ) -> dict:
        """Store the developer's last feature, files, and mental model."""

        return run_remember_work(
            feature=feature,
            files=files,
            mental_model=mental_model,
            notes=notes,
            repo_path=repo_path,
            state_manager=manager,
        )

    @mcp.tool
    def resume_context(repo_path: str | None = None) -> dict:
        """Return the last known working context plus a quick repo summary."""

        return run_resume_context(repo_path=repo_path, state_manager=manager)
