"""Backward-compatible wrapper for repository MCP tools.

This module keeps legacy imports stable by re-exporting scan tool helpers from
``cartographer.services.tools.repo_tools``.
"""

from cartographer.services.tools.repo_tools import register_repo_tools, run_scan_repo

__all__ = ["register_repo_tools", "run_scan_repo"]
