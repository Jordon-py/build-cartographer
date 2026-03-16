"""Read-only file helpers used to extract lightweight repository context.

These helpers support intent and impact heuristics by safely reading text,
finding README content, and filtering paths for text-like files.
"""

from __future__ import annotations

from pathlib import Path

from cartographer.config import README_FILE_NAMES, TEXT_FILE_SUFFIXES


def read_text_file(path: str | Path, max_chars: int | None = 50000) -> str | None:
    # Read text files defensively so heuristics do not fail on odd encodings.
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
    except OSError:
        return None

    if max_chars is not None:
        return text[:max_chars]
    return text


def read_readme(root: str | Path) -> str | None:
    # Scan a few common README names and return the first readable project overview.
    root_path = Path(root)
    for candidate in README_FILE_NAMES:
        readme_path = root_path / candidate
        text = read_text_file(readme_path, max_chars=20000)
        if text:
            return text
    return None


def is_text_like(path: str | Path) -> bool:
    # Limit cheap content searches to files that are likely to contain importable text.
    suffix = Path(path).suffix.lower()
    return suffix in TEXT_FILE_SUFFIXES or Path(path).name.startswith(".env")
