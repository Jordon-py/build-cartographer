import asyncio
import tempfile
import unittest
from pathlib import Path

from cartographer.server import create_server
from cartographer.state import StateManager


class ServerSmokeTests(unittest.TestCase):
    def test_server_registers_expected_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(StateManager(Path(temp_dir) / "state.json"))

            scan_tool = asyncio.run(server.get_tool("scan_repo"))
            summary_tool = asyncio.run(server.get_tool("repo_summary"))
            intent_tool = asyncio.run(server.get_tool("summarize_intent"))
            impact_tool = asyncio.run(server.get_tool("impact_view"))
            next_steps_tool = asyncio.run(server.get_tool("suggest_next_steps"))
            remember_tool = asyncio.run(server.get_tool("remember_work"))
            resume_tool = asyncio.run(server.get_tool("resume_context"))

            self.assertIsNotNone(scan_tool)
            self.assertIsNotNone(summary_tool)
            self.assertIsNotNone(intent_tool)
            self.assertIsNotNone(impact_tool)
            self.assertIsNotNone(next_steps_tool)
            self.assertIsNotNone(remember_tool)
            self.assertIsNotNone(resume_tool)


if __name__ == "__main__":
    unittest.main()
