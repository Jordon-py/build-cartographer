import tempfile
import unittest
from pathlib import Path

from cartographer.resources import read_readme
from cartographer.services.impact_analyzer import estimate_change_impact
from cartographer.services.intent_ledger import summarize_intent
from cartographer.services.repo_scanner import scan_repo
from cartographer.services.tools.planning_tools import (
    run_impact_view,
    run_remember_work,
    run_repo_summary,
    run_resume_context,
    run_suggest_next_steps,
    run_summarize_intent,
)
from cartographer.services.tools.repo_tools import run_scan_repo
from cartographer.state import StateManager


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ServiceFlowTests(unittest.TestCase):
    def test_repo_scan_intent_and_impact_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write(root / "README.md", "# NFL Predictor\nReact + FastAPI app for NFL prediction.\n")
            _write(root / "pyproject.toml", '[project]\nname = "nfl-predictor"\ndependencies = ["fastapi", "pydantic"]\n')
            _write(root / ".env.example", "API_KEY=demo\n")
            _write(root / "backend" / "main.py", "from fastapi import FastAPI\nfrom backend.routes.picks import router\napp = FastAPI()\n")
            _write(
                root / "backend" / "routes" / "picks.py",
                "from backend.models.prediction_model import PredictionModel\nrouter = object()\n",
            )
            _write(root / "backend" / "models" / "prediction_model.py", "class PredictionModel:\n    pass\n")
            _write(root / "frontend" / "src" / "App.tsx", "export default function App() { return <div>NFL</div>; }\n")

            repo_map = scan_repo(root)
            self.assertEqual(repo_map.project_name, "nfl-predictor")
            self.assertIn("pyproject.toml", repo_map.config_files)
            self.assertIn(".env.example", repo_map.env_files)
            self.assertIn("backend/routes/picks.py", repo_map.route_files)
            self.assertIn("backend/models/prediction_model.py", repo_map.schema_files)
            self.assertIn("FastAPI", repo_map.technologies)

            intent = summarize_intent(repo_map, readme_text=read_readme(root))
            self.assertIn("NFL prediction", intent.summary)

            impact = estimate_change_impact("backend/models/prediction_model.py", repo_map)
            self.assertIn("backend/routes/picks.py", impact.imported_by)
            self.assertEqual(impact.layer, "Data / domain")

    def test_tool_wrappers_update_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "memory.json"
            manager = StateManager(state_file)

            _write(root / "README.md", "# Demo\nA small FastAPI service.\n")
            _write(root / "pyproject.toml", '[project]\nname = "demo-service"\ndependencies = ["fastapi"]\n')
            _write(root / "app" / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")

            scan_result = run_scan_repo(str(root), state_manager=manager)
            self.assertEqual(scan_result["repo_map"]["project_name"], "demo-service")

            repo_summary = run_repo_summary(state_manager=manager)
            self.assertEqual(repo_summary["project_name"], "demo-service")
            self.assertTrue(repo_summary["recent_changes_that_matter"])
            self.assertTrue(repo_summary["recent_changes_that_matter"][0]["reason"])

            intent_result = run_summarize_intent(state_manager=manager)
            self.assertIn("FastAPI", intent_result["intent_summary"]["summary"])

            impact_result = run_impact_view("app/main.py", state_manager=manager)
            self.assertEqual(impact_result["impact_report"]["target"], "app/main.py")

            remember_result = run_remember_work(
                feature="Add auth middleware",
                files=["app/main.py"],
                mental_model="The main app is the integration point for middleware and routes.",
                state_manager=manager,
            )
            self.assertEqual(
                remember_result["project_state"]["last_worked_on_feature"],
                "Add auth middleware",
            )

            resume_result = run_resume_context(state_manager=manager)
            self.assertEqual(
                resume_result["resume_context"]["last_worked_on_feature"],
                "Add auth middleware",
            )
            self.assertEqual(
                resume_result["resume_context"]["last_worked_on_files"],
                ["app/main.py"],
            )
            self.assertEqual(
                resume_result["resume_context"]["mental_model"],
                "The main app is the integration point for middleware and routes.",
            )
            self.assertEqual(resume_result["repo_summary"]["project_name"], "demo-service")

            next_steps_result = run_suggest_next_steps(state_manager=manager)
            self.assertTrue(next_steps_result["next_steps"])
            self.assertIn("Resume work", next_steps_result["next_steps"][0]["step"])
            self.assertEqual(manager.load().project_name, "demo-service")


if __name__ == "__main__":
    unittest.main()
