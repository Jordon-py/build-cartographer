"""Core Pydantic models shared by Cartographer scanning, planning, and memory tools.

This module defines:
- request/response contracts for scanning and analysis,
- the persisted project state schema,
- small path/time helpers used across the server.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cartographer.config import DEFAULT_EXCLUDE_PATTERNS

Priority = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ProjectPhase = Literal["idle", "scanning", "mapped", "analyzing", "ready", "blocked"]


def utc_now() -> datetime:
    # Keep timestamps timezone-aware so persisted memory remains unambiguous.
    return datetime.now(timezone.utc)


def normalize_path(value: str | Path | None) -> Path:
    # Normalize user and relative paths into a stable absolute form.
    if value in (None, ""):
        return Path.cwd().resolve()
    return Path(value).expanduser().resolve(strict=False)


class CartographerModel(BaseModel):
    """Shared settings for all Cartographer models."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class RepoScanRequest(CartographerModel):
    """Input contract for repository scanning."""

    repo_path: Path = Field(default_factory=Path.cwd, description="Repository directory to scan.")
    include_patterns: list[str] = Field(default_factory=list, description="Optional glob patterns to include.")
    exclude_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS),
        description="Directories or globs to skip during scanning.",
    )
    max_depth: int | None = Field(default=None, ge=0, description="Maximum scan depth.")

    @field_validator("repo_path", mode="before")
    @classmethod
    def normalize_repo_path(cls, value: str | Path | None) -> Path:
        # Resolve path input before type-level validation.
        return normalize_path(value)

    @field_validator("repo_path")
    @classmethod
    def ensure_directory(cls, value: Path) -> Path:
        # Reject file paths to keep scanner behavior predictable.
        if value.exists() and not value.is_dir():
            raise ValueError("repo_path must point to a directory")
        return value


class RepoMap(CartographerModel):
    """Structured repository map produced by `scan_repo`."""

    root_path: Path = Field(description="Resolved repository root.")
    project_name: str | None = Field(default=None, description="Best-known project name.")
    summary: str = Field(default="", description="Short overview of the repository.")
    directories: list[str] = Field(default_factory=list, description="Directories found while scanning.")
    files: list[str] = Field(default_factory=list, description="Files found while scanning.")
    file_types: dict[str, int] = Field(default_factory=dict, description="Counts by file extension.")
    entrypoints: list[str] = Field(default_factory=list, description="Likely application entrypoints.")
    config_files: list[str] = Field(default_factory=list, description="Config and infrastructure files.")
    env_files: list[str] = Field(default_factory=list, description="Environment files such as .env.")
    route_files: list[str] = Field(default_factory=list, description="Files that likely define routes.")
    schema_files: list[str] = Field(default_factory=list, description="Schema, model, DTO, or entity files.")
    recent_files: list[str] = Field(default_factory=list, description="Most recently modified files.")
    technologies: list[str] = Field(default_factory=list, description="Detected frameworks or libraries.")
    warnings: list[str] = Field(default_factory=list, description="Problems noticed during scanning.")
    generated_at: datetime = Field(default_factory=utc_now, description="When the repo map was created.")

    @field_validator("root_path", mode="before")
    @classmethod
    def normalize_root_path(cls, value: str | Path | None) -> Path:
        # Normalize root paths once so downstream tools can compare safely.
        return normalize_path(value)

    @field_validator("root_path")
    @classmethod
    def ensure_root_directory(cls, value: Path) -> Path:
        # Guard against accidentally passing a file as repository root.
        if value.exists() and not value.is_dir():
            raise ValueError("root_path must point to a directory")
        return value


class IntentSummary(CartographerModel):
    """Heuristic summary of what the project appears to be."""

    user_goal: str = Field(default="", description="Original user goal if known.")
    summary: str = Field(description="Condensed interpretation of project intent.")
    intent_type: str = Field(default="unknown", description="General category of work or project.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in the summary.")
    evidence: list[str] = Field(default_factory=list, description="Signals used to produce the summary.")
    open_questions: list[str] = Field(default_factory=list, description="Unknowns that still need answers.")
    affected_paths: list[str] = Field(default_factory=list, description="Likely paths in scope for the intent.")


class ImpactReport(CartographerModel):
    """Heuristic estimate of what a change may affect."""

    target: str = Field(description="File path or symbol being analyzed.")
    summary: str = Field(description="Short impact summary.")
    layer: str | None = Field(default=None, description="Architecture layer likely affected.")
    risk_level: RiskLevel = Field(default="medium", description="Estimated change risk.")
    imports: list[str] = Field(default_factory=list, description="Dependencies imported by the target.")
    imported_by: list[str] = Field(default_factory=list, description="Files that appear to reference the target.")
    folders: list[str] = Field(default_factory=list, description="Parent folders containing the target.")
    affected_paths: list[str] = Field(default_factory=list, description="Likely files or folders impacted.")
    concerns: list[str] = Field(default_factory=list, description="Likely follow-on risks or questions.")
    test_recommendations: list[str] = Field(default_factory=list, description="Helpful validation steps.")


class NextStepSuggestion(CartographerModel):
    """A recommended next action generated from current project state."""

    step: str = Field(description="Suggested next action.")
    reason: str = Field(description="Why the step matters right now.")
    priority: Priority = Field(default="medium", description="Suggested urgency.")
    target_paths: list[str] = Field(default_factory=list, description="Relevant files or folders for the step.")


class ProjectState(CartographerModel):
    """Long-term project memory persisted to disk."""

    phase: ProjectPhase = Field(default="idle", description="Current stage of repository analysis.")
    repo_path: Path | None = Field(default=None, description="Tracked repository path.")
    project_name: str | None = Field(default=None, description="Best-known project name.")
    last_scan_time: datetime | None = Field(default=None, description="When the last scan completed.")
    recent_files_changed: list[str] = Field(default_factory=list, description="Most recently modified files.")
    latest_inferred_intent: str | None = Field(default=None, description="Latest plain-language intent summary.")
    open_questions: list[str] = Field(default_factory=list, description="Outstanding project questions.")
    unfinished_work: list[str] = Field(default_factory=list, description="Known pending work items.")
    last_worked_on_feature: str | None = Field(default=None, description="Last feature or task the developer worked on.")
    last_worked_on_files: list[str] = Field(default_factory=list, description="Files from the latest work session.")
    mental_model: str | None = Field(default=None, description="Short reminder of the developer's last mental model.")
    repo_scan_request: RepoScanRequest | None = Field(default=None, description="Latest scan request.")
    repo_map: RepoMap | None = Field(default=None, description="Latest repository map.")
    intent_summary: IntentSummary | None = Field(default=None, description="Latest inferred project intent.")
    impact_report: ImpactReport | None = Field(default=None, description="Latest impact analysis result.")
    next_steps: list[NextStepSuggestion] = Field(default_factory=list, description="Recommended next actions.")
    notes: list[str] = Field(default_factory=list, description="Freeform working notes.")
    updated_at: datetime = Field(default_factory=utc_now, description="When the state was last updated.")

    @field_validator("repo_path", mode="before")
    @classmethod
    def normalize_state_repo_path(cls, value: str | Path | None) -> Path | None:
        # Keep repo_path normalized whenever state is loaded or updated.
        if value is None:
            return None
        return normalize_path(value)


__all__ = [
    "CartographerModel",
    "ImpactReport",
    "IntentSummary",
    "NextStepSuggestion",
    "Priority",
    "ProjectPhase",
    "ProjectState",
    "RepoMap",
    "RepoScanRequest",
    "RiskLevel",
    "normalize_path",
    "utc_now",
]
