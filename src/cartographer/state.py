"""JSON-backed project memory for Cartographer.

This module persists and retrieves `ProjectState` so tool outputs can remain
grounded across sessions, including remembered developer context.
"""

from __future__ import annotations

import json
from pathlib import Path

from cartographer.config import DEFAULT_STATE_FILE
from cartographer.models import (
    ImpactReport,
    IntentSummary,
    NextStepSuggestion,
    ProjectState,
    RepoMap,
    RepoScanRequest,
    normalize_path,
)


def _dedupe(items: list[str]) -> list[str]:
    # Preserve order while dropping blank or repeated strings from updates.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


class StateManager:
    """Simple JSON state manager used by scanning and planning tools."""

    def __init__(self, state_file: str | Path | None = None) -> None:
        # Allow temporary state files in tests while keeping one default path in production.
        self.state_file = Path(state_file or DEFAULT_STATE_FILE)

    def load(self) -> ProjectState:
        # Return an empty state when no persisted memory exists yet.
        if not self.state_file.exists():
            return ProjectState()
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        return ProjectState.model_validate(data)

    def save(self, state: ProjectState) -> ProjectState:
        # Persist the state in JSON mode so datetimes/paths are serialized safely.
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump(mode="json")
        self.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return state

    def update(self, **changes: object) -> ProjectState:
        # Apply a partial update to the current state, then persist it.
        updated = self.load().model_copy(update=changes)
        return self.save(updated)

    def remember_repo(
        self,
        repo_path: str | Path,
        *,
        project_name: str | None = None,
        repo_scan_request: RepoScanRequest | None = None,
    ) -> ProjectState:
        # Store canonical repo identity so other tools can run without repeated path arguments.
        resolved_path = normalize_path(repo_path)
        return self.update(
            repo_path=resolved_path,
            project_name=project_name or resolved_path.name,
            repo_scan_request=repo_scan_request,
        )

    def record_scan(self, repo_map: RepoMap, request: RepoScanRequest | None = None) -> ProjectState:
        # Promote scan output into persistent project memory.
        return self.update(
            phase="mapped",
            repo_path=repo_map.root_path,
            project_name=repo_map.project_name or repo_map.root_path.name,
            last_scan_time=repo_map.generated_at,
            recent_files_changed=repo_map.recent_files,
            repo_scan_request=request,
            repo_map=repo_map,
        )

    def record_intent(self, intent_summary: IntentSummary) -> ProjectState:
        # Persist inferred intent and merge any newly surfaced open questions.
        state = self.load()
        return self.update(
            phase="analyzing",
            latest_inferred_intent=intent_summary.summary,
            open_questions=_dedupe(state.open_questions + intent_summary.open_questions),
            intent_summary=intent_summary,
        )

    def record_impact(self, impact_report: ImpactReport) -> ProjectState:
        # Persist the latest impact report for review and planning flows.
        return self.update(
            impact_report=impact_report,
            phase="ready",
        )

    def record_next_steps(self, next_steps: list[NextStepSuggestion]) -> ProjectState:
        # Convert suggested steps into unfinished work so progress survives sessions.
        unfinished_work = _dedupe([step.step for step in next_steps])
        return self.update(
            next_steps=next_steps,
            unfinished_work=unfinished_work,
            phase="ready",
        )

    def remember_work(
        self,
        *,
        feature: str | None = None,
        files: list[str] | None = None,
        mental_model: str | None = None,
        notes: list[str] | None = None,
    ) -> ProjectState:
        # Persist a lightweight "what I was doing" snapshot for fast re-entry.
        state = self.load()
        return self.update(
            last_worked_on_feature=feature or state.last_worked_on_feature,
            last_worked_on_files=_dedupe(files or state.last_worked_on_files),
            mental_model=mental_model or state.mental_model,
            notes=_dedupe(state.notes + (notes or [])),
        )

    def add_open_questions(self, questions: list[str]) -> ProjectState:
        # Append questions without losing earlier ones.
        state = self.load()
        return self.update(open_questions=_dedupe(state.open_questions + questions))

    def add_notes(self, notes: list[str]) -> ProjectState:
        # Append notes while keeping them deduplicated.
        state = self.load()
        return self.update(notes=_dedupe(state.notes + notes))

    def resume_context(self) -> dict:
        # Return the highest-signal fields needed to resume project work quickly.
        state = self.load()
        return {
            "project_name": state.project_name,
            "repo_path": str(state.repo_path) if state.repo_path else None,
            "latest_inferred_intent": state.latest_inferred_intent,
            "recent_files_changed": state.recent_files_changed,
            "open_questions": state.open_questions,
            "unfinished_work": state.unfinished_work,
            "last_worked_on_feature": state.last_worked_on_feature,
            "last_worked_on_files": state.last_worked_on_files,
            "mental_model": state.mental_model,
            "next_steps": [step.model_dump(mode="json") for step in state.next_steps],
            "notes": state.notes,
        }
