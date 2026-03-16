import tempfile
import unittest
from pathlib import Path

from cartographer.models import IntentSummary, RepoMap, RepoScanRequest
from cartographer.state import StateManager


class StateManagerTests(unittest.TestCase):
    def test_persists_project_memory_to_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            manager = StateManager(state_file)

            repo_map = RepoMap(
                root_path=temp_dir,
                project_name="demo-app",
                summary="Temporary demo repository.",
                files=["app/main.py"],
                recent_files=["app/main.py"],
                entrypoints=["app/main.py"],
            )

            manager.remember_repo(temp_dir, project_name="demo-app", repo_scan_request=RepoScanRequest(repo_path=temp_dir))
            manager.record_scan(repo_map)
            manager.record_intent(
                IntentSummary(
                    summary="This appears to be a demo Python application.",
                    intent_type="application",
                    open_questions=["What data source does it use?"],
                )
            )
            manager.remember_work(
                feature="Wire the API client",
                files=["app/main.py", "app/client.py"],
                mental_model="The main app boots first, then the client layer wires outbound requests.",
            )

            loaded = manager.load()
            resume_context = manager.resume_context()

            self.assertEqual(loaded.project_name, "demo-app")
            self.assertEqual(loaded.repo_path, Path(temp_dir).resolve())
            self.assertEqual(loaded.recent_files_changed, ["app/main.py"])
            self.assertEqual(loaded.latest_inferred_intent, "This appears to be a demo Python application.")
            self.assertEqual(loaded.open_questions, ["What data source does it use?"])
            self.assertEqual(loaded.last_worked_on_feature, "Wire the API client")
            self.assertEqual(resume_context["last_worked_on_files"], ["app/main.py", "app/client.py"])
            self.assertTrue(state_file.exists())


if __name__ == "__main__":
    unittest.main()
