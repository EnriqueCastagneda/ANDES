"""Regenera la sección de descargas del README para una versión publicada.

Uso: python scripts/update_readme_downloads.py <owner/repo> <tag> [README.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

START = "<!-- DOWNLOADS:START -->"
END = "<!-- DOWNLOADS:END -->"

TARGETS = [
    ("Linux", "linux", ".tar.gz"),
    ("Windows", "windows", ".zip"),
    ("macOS", "macos", ".zip"),
    ("Android (APK)", "apk", ".zip"),
    ("Web", "web", ".zip"),
]


def build_section(repo: str, tag: str) -> str:
    version = tag.removeprefix("v")
    base = f"https://github.com/{repo}/releases"
    lines = [
        f"Descarga los archivos de la versión [{tag}]({base}/tag/{tag}):",
        "",
        "| Plataforma | Descarga |",
        "| --- | --- |",
    ]
    for label, target, ext in TARGETS:
        name = f"bcrp-downloader-{target}-{version}{ext}"
        lines.append(f"| {label} | [{name}]({base}/download/{tag}/{name}) |")
    lines += [
        "",
        f"Consulta la página de [releases]({base}) para descargar otras versiones.",
    ]
    return "\n".join(lines)


def update(text: str, repo: str, tag: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit("Marcadores DOWNLOADS no encontrados en el README")
    block = f"{START}\n{build_section(repo, tag)}\n{END}"
    return pattern.sub(lambda _: block, text)


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        raise SystemExit(__doc__)
    repo, tag = argv[1], argv[2]
    path = Path(argv[3] if len(argv) > 3 else "README.md")
    path.write_text(update(path.read_text(encoding="utf-8"), repo, tag), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
