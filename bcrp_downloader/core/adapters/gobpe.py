"""Adaptador de portales estadísticos de Gob.pe.

Indexa el registro descubierto por ``core.gobpe`` como un catálogo de portales.
Solo los destinos tabulares (CSV, Excel, API/JSON) se pueden descargar; los
tableros y páginas web se ofrecen como enlace externo.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

import pandas as pd
import requests

from .. import catalog, gobpe
from ..paths import DATA_DIR

CACHE_DIR = os.path.join(DATA_DIR, "gobpe", "files")
INDEX_STAMP = os.path.join(DATA_DIR, "gobpe", "indexed.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (bcrp-downloader)"}
_FILE_TTL = 7 * 86400


class GobpeAdapter:
    """Portales publicados por las entidades del Estado peruano."""

    institution = "gobpe"

    def __init__(self) -> None:
        self._spec = None

    # ------------------------------------------------------------------ #
    @staticmethod
    def _digest(portals: list[dict]) -> str:
        payload = json.dumps(
            [[portal.get("id"), portal.get("institution_id")] for portal in portals],
            sort_keys=True,
        )
        return hashlib.sha1(payload.encode()).hexdigest()

    def _ensure_indexed(self, force: bool = False) -> int:
        portals = gobpe.load_registry()
        if not portals:
            return 0
        digest = self._digest(portals)
        stamped = ""
        if os.path.exists(INDEX_STAMP):
            try:
                with open(INDEX_STAMP, encoding="utf-8") as handle:
                    stamped = json.load(handle).get("digest", "")
            except (ValueError, OSError):
                stamped = ""
        if (
            not force
            and stamped == digest
            and catalog.count_prefix("GOBPE-") == len(portals)
        ):
            return 0
        catalog.clear_prefix("GOBPE-")
        rows: list[dict] = []
        for portal in portals:
            rows.append(
                {
                    "institution": f"gobpe:{portal['institution_id']}",
                    "code": portal["id"],
                    "category": portal.get("platform", "web"),
                    "group_name": portal.get("kind", "") or "Portal",
                    "name": portal.get("name", ""),
                    "description": portal.get("url", ""),
                    "unit": "",
                    "source": "Gob.pe",
                    "frequency": "Portal",
                    "pub_group": portal.get("scope", ""),
                    "area": portal.get("institution", ""),
                    "start": "",
                    "end": "",
                    "memo": json.dumps(
                        {
                            "kind": "gobpe",
                            "url": portal.get("url", ""),
                            "platform": portal.get("platform", "web"),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        written = catalog.upsert(rows)
        os.makedirs(os.path.dirname(INDEX_STAMP), exist_ok=True)
        with open(INDEX_STAMP, "w", encoding="utf-8") as handle:
            json.dump({"digest": digest, "count": len(rows)}, handle)
        return written

    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        *,
        filters: dict | None = None,
        limit: int | None = 300,
    ) -> pd.DataFrame:
        from .. import metadata

        self._ensure_indexed()
        scoped = dict(filters or {})
        return metadata.search_catalog(query, filters=scoped, limit=limit)

    def _download(self, url: str) -> tuple[str, str]:
        os.makedirs(CACHE_DIR, exist_ok=True)
        digest = hashlib.sha1(url.encode()).hexdigest()[:16]
        extension = gobpe.classify(url)
        suffix = {"csv": "csv", "excel": "xlsx", "api": "json", "ckan": "json"}.get(
            extension, "bin"
        )
        path = os.path.join(CACHE_DIR, f"{digest}.{suffix}")
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < _FILE_TTL:
            return path, suffix
        response = requests.get(url, headers=HEADERS, timeout=180)
        response.raise_for_status()
        with open(path, "wb") as handle:
            handle.write(response.content)
        return path, suffix

    @staticmethod
    def _parse(path: str, suffix: str) -> pd.DataFrame:
        from .inei_tematico import IneiTematicoAdapter

        if suffix in ("csv", "xlsx"):
            return IneiTematicoAdapter._table(path, suffix)
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        records = payload
        if isinstance(payload, dict):
            for key in ("records", "results", "data", "datos"):
                if isinstance(payload.get(key), list):
                    records = payload[key]
                    break
        if isinstance(records, list) and records:
            return pd.DataFrame(records)
        return pd.DataFrame()

    def fetch(
        self,
        codes: list[str],
        start: str = "archivo",
        end: str = "unico",
        frequency: str | None = None,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for code in codes:
            row = catalog.get(code)
            if not row or not row.get("memo"):
                continue
            try:
                memo = json.loads(row["memo"])
            except (TypeError, ValueError):
                continue
            if memo.get("platform") not in gobpe.TABULAR:
                continue
            try:
                path, suffix = self._download(memo["url"])
                frame = self._parse(path, suffix)
            except Exception:
                continue
            if frame.empty:
                continue
            frames.append(frame)
        if not frames:
            return pd.DataFrame()
        if len(frames) == 1:
            return frames[0]
        return pd.concat(frames, ignore_index=True)

    def info(self, code: str) -> dict:
        row = catalog.get(code) or {}
        return {
            "institution": "gobpe",
            "code": code,
            "source": "Gob.pe",
            "name": row.get("name", ""),
            "url": row.get("description", ""),
            "updated": time.strftime("%Y-%m-%d"),
        }