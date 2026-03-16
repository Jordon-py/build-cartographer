import os
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from cartographer.models import (
    ImpactReport,
    IntentSummary,
    NextStepSuggestion,
    ProjectState,
    RepoMap,
    RepoScanRequest,
)


class RepoScanRequestTests(unittest.TestCase):
    def test_defaults_to_current_working_directory(self) -> None:
        request = RepoScanRequest()

        self.assertEqual(request.repo_path, Path.cwd().resolve())
        self.assertIn(".git", request.exclude_patterns)

    def test_resolves_relative_paths(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                request = RepoScanRequest(repo_path=".")
            finally:
                os.chdir(original_cwd)

        self.assertEqual(request.repo_path, Path(temp_dir).resolve())

    def test_rejects_file_paths(self) -> None:
        with tempfile.NamedTemporaryFile() as temp_file:
            with self.assertRaises(ValidationError):
                RepoScanRequest(repo_path=temp_file.name)


class ProjectStateTests(unittest.TestCase):
    def test_nested_models_dump_cleanly(self) -> None:
        repo_map = RepoMap(
            root_path=Path.cwd(),
            project_name="build-cartographer",
            summary="Python MCP server scaffold.",
            files=["src/cartographer/models.py", "src/cartographer/server.py"],
            entrypoints=["src/cartographer/server.py"],
            schema_files=["src/cartographer/models.py"],
            technologies=["Python", "Pydantic"],
        )
        intent = IntentSummary(
            summary="This appears to be a Python MCP server for repository analysis.",
            intent_type="service",
            confidence=0.9,
            evidence=["Detected Python files and FastMCP usage."],
            open_questions=["Which repo should be scanned first?"],
            affected_paths=["src/cartographer/server.py"],
        )
        impact = ImpactReport(
            target="src/cartographer/server.py",
            summary="Server changes affect MCP tool registration.",
            layer="Application",
            risk_level="medium",
            imported_by=["src/build_cartographer/__init__.py"],
            affected_paths=["src/cartographer/server.py", "src/build_cartographer/__init__.py"],
        )
        state = ProjectState(
            phase="ready",
            repo_path=Path.cwd(),
            project_name="build-cartographer",
            latest_inferred_intent=intent.summary,
            open_questions=intent.open_questions,
            unfinished_work=["Wire up repository tools"],
            last_worked_on_feature="Resume MCP planning flow",
            last_worked_on_files=["src/cartographer/server.py"],
            mental_model="The server composes repo tools and planning tools around one shared state manager.",
            repo_scan_request=RepoScanRequest(),
            repo_map=repo_map,
            intent_summary=intent,
            impact_report=impact,
            next_steps=[
                NextStepSuggestion(
                    step="Run the server",
                    reason="Verify the registered MCP tools can load.",
                    priority="high",
                    target_paths=["src/cartographer/server.py"],
                )
            ],
        )

        dumped = state.model_dump(mode="json")

        self.assertEqual(dumped["phase"], "ready")
        self.assertEqual(dumped["repo_map"]["entrypoints"][0], "src/cartographer/server.py")
        self.assertEqual(dumped["impact_report"]["target"], "src/cartographer/server.py")
        self.assertEqual(dumped["open_questions"][0], "Which repo should be scanned first?")
        self.assertEqual(dumped["last_worked_on_feature"], "Resume MCP planning flow")


if __name__ == "__main__":
    unittest.main()
