"""Central constants and heuristics used by scanner and planning services.

This module defines stable defaults (state-file path, exclude patterns, and
filename hints) that keep repository analysis predictable across tools.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_FILE = PROJECT_ROOT / ".cartographer_state.json"
DEFAULT_EXCLUDE_PATTERNS = (".git", ".venv", "__pycache__", "node_modules")

README_FILE_NAMES = ("README.md", "README.rst", "README.txt")
TEXT_FILE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".env",
}

ENTRYPOINT_FILE_NAMES = {
    "main.py",
    "app.py",
    "server.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "index.js",
    "index.ts",
    "index.jsx",
    "index.tsx",
    "main.js",
    "main.ts",
    "main.jsx",
    "main.tsx",
}

CONFIG_FILE_NAMES = {
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.ts",
    "tailwind.config.js",
    "tailwind.config.ts",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    "alembic.ini",
}

ROUTE_HINTS = ("route", "routes", "router", "urls", "page", "pages", "api")
SCHEMA_HINTS = ("schema", "schemas", "model", "models", "entity", "entities", "dto", "serializer")
