"""Intent inference service for converting repo facts into project summaries.

This module turns scan outputs plus README text into concise intent context
that powers quick re-entry and grounded planning suggestions.
"""

from __future__ import annotations

from cartographer.models import IntentSummary, RepoMap


def infer_project_intent(file_names: list[str], readme_text: str | None) -> str:
    # Blend file-name clues with README language to get a quick project hypothesis.
    names_blob = " ".join(file_names).lower()
    readme_blob = (readme_text or "").lower()
    signal_blob = f"{names_blob} {readme_blob}".strip()

    stack: list[str] = []
    if "react" in signal_blob or any(name.endswith((".tsx", ".jsx")) for name in file_names):
        stack.append("React")
    if "fastapi" in signal_blob:
        stack.append("FastAPI")
    elif "django" in signal_blob:
        stack.append("Django")
    elif "flask" in signal_blob:
        stack.append("Flask")

    stack_text = " + ".join(stack)

    if any(keyword in signal_blob for keyword in ("nfl", "prediction", "predictions", "forecast")):
        subject = "app for NFL prediction"
    elif any(keyword in signal_blob for keyword in ("dashboard", "admin", "report", "reporting")):
        subject = "internal admin dashboard with auth and reporting"
    elif any(keyword in signal_blob for keyword in ("publish", "publishing", "content", "cms", "article")):
        subject = "content publishing app"
    elif any(keyword in signal_blob for keyword in ("auth", "login", "user", "account")):
        subject = "application with authentication"
    else:
        subject = "application"

    if stack_text and subject == "application":
        return f"This appears to be a {stack_text} application."
    if stack_text:
        return f"This appears to be a {stack_text} {subject}."
    if subject != "application":
        return f"This repository appears to be a {subject}."
    return "This repository appears to be a software project."


def summarize_intent(repo_map: RepoMap, readme_text: str | None = None, user_goal: str = "") -> IntentSummary:
    # Turn raw scan facts into a summary the next planning step can actually use.
    summary = infer_project_intent(repo_map.files, readme_text)
    evidence: list[str] = []
    open_questions: list[str] = []

    if repo_map.technologies:
        evidence.append(f"Detected technologies: {', '.join(repo_map.technologies)}")
    if repo_map.entrypoints:
        evidence.append(f"Found likely entrypoints: {', '.join(repo_map.entrypoints[:3])}")
    if repo_map.route_files:
        evidence.append(f"Found route files: {', '.join(repo_map.route_files[:3])}")
    if repo_map.schema_files:
        evidence.append(f"Found schema/model files: {', '.join(repo_map.schema_files[:3])}")

    if not readme_text:
        open_questions.append("README is missing or does not describe the project clearly.")
    if not repo_map.entrypoints:
        open_questions.append("Primary runtime entrypoint is still unclear.")

    if repo_map.route_files:
        intent_type = "application"
    elif "library" in summary.lower():
        intent_type = "library"
    else:
        intent_type = "service"

    affected_paths = repo_map.entrypoints[:3] + repo_map.route_files[:3] + repo_map.schema_files[:3]
    confidence = 0.85 if evidence else 0.5

    return IntentSummary(
        user_goal=user_goal,
        summary=summary,
        intent_type=intent_type,
        confidence=confidence,
        evidence=evidence,
        open_questions=open_questions,
        affected_paths=affected_paths,
    )
