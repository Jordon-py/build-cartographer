"""MCP tool wrappers for repository-scanning workflows.

This module exposes the `scan_repo` tool and persists scan output so later
summary/impact/planning tools stay grounded in current repository state.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from cartographer.models import RepoScanRequest
from cartographer.services.repo_scanner import scan_repo as build_repo_map
from cartographer.state import StateManager


def run_scan_repo(repo_path: str, state_manager: StateManager | None = None) -> dict:
    # Build a repo map and immediately persist it so later tools can reuse the context.
    manager = state_manager or StateManager()
    request = RepoScanRequest(repo_path=Path(repo_path))
    repo_map = build_repo_map(request)
    project_state = manager.record_scan(repo_map, request=request)
    return {
        "repo_map": repo_map.model_dump(mode="json"),
        "project_state": project_state.model_dump(mode="json"),
    }


def register_repo_tools(mcp: FastMCP, state_manager: StateManager | None = None) -> None:
    # Keep scan registration separate so the server composition stays easy to follow.
    manager = state_manager or StateManager()

    @mcp.tool
    def scan_repo(repo_path: str) -> dict:
        """Scan a repository and store the resulting project memory."""

        return run_scan_repo(repo_path, state_manager=manager)
