"""MCP server composition for Cartographer.

This module wires repository and planning tools onto one FastMCP instance so
clients can call scan, summary, impact, next-step, and resume-memory flows.
"""

from __future__ import annotations

from fastmcp import FastMCP

from cartographer.services.tools.planning_tools import register_planning_tools
from cartographer.services.tools.repo_tools import register_repo_tools
from cartographer.state import StateManager


def create_server(state_manager: StateManager | None = None) -> FastMCP:
    # Compose the MCP server in one place so tool registration stays easy to audit.
    manager = state_manager or StateManager()
    mcp = FastMCP(
        name="Cartographer",
        instructions=(
            "Cartographer scans repositories, remembers project context over time, "
            "infers project intent, estimates change impact, and suggests next steps."
        ),
    )
    register_repo_tools(mcp, manager)
    register_planning_tools(mcp, manager)
    return mcp


mcp = create_server()


def main() -> None:
    # Run the assembled MCP server with stdio transport for local MCP clients.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
