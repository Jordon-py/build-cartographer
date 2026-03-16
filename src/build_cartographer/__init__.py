"""Package entrypoint that runs the Cartographer MCP server."""

from cartographer.server import main as run_server


def main() -> None:
    # Reuse the server entrypoint so the package script and module stay in sync.
    run_server()
