"""Garantiza que la app y su documentación usen solo herramientas locales."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = ("tiny" + "fish", "fire" + "crawl", "miro" + "fish")
SKIP_DIRS = {
    ".git", "__pycache__", "data", "dist", "outputs",
    "node_modules", ".pytest_cache", ".ruff_cache",
}
SUFFIXES = {".py", ".md", ".toml", ".txt", ".json", ".yml", ".yaml", ".sh"}


def test_no_external_agent_references():
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if any(part in SKIP_DIRS or part.endswith(".egg-info")
               for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for name in FORBIDDEN:
            if name in text:
                hits.append(f"{path.relative_to(ROOT)}: {name}")
    assert not hits, hits