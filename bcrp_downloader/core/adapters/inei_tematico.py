"""Índice temático del INEI: archivos de datos por categoría.

El portal publica un índice con ocho categorías. Cada categoría enlaza
archivos (``.xls``, ``.xlsx``, ``.xlsm``, ``.csv``) con sus cuadros. Este
adaptador descubre esas categorías y archivos en tiempo de ejecución, los
cachea y los indexa en el catálogo local como un registro descargable por
archivo. No hay lista fija: si el INEI agrega o quita archivos, el índice se
reconstruye en la siguiente actualización.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from html.parser import HTMLParser

import pandas as pd
import requests

from .. import catalog
from ..paths import DATA_DIR
from ..portals import spec_for

INDEX_URL = "https://www.inei.gob.pe/estadisticas-indice-tematico/"
CACHE_DIR = os.path.join(DATA_DIR, "inei_tematico")
INDEX_CACHE = os.path.join(CACHE_DIR, "index.json")
FILES_DIR = os.path.join(CACHE_DIR, "files")
HEADERS = {"User-Agent": "Mozilla/5.0 (bcrp-downloader)"}
TABLE_EXTS = ("xls", "xlsx", "xlsm", "csv")
_INDEX_TTL = 7 * 86400
_FILE_TTL = 30 * 86400
_FILE_RE = re.compile(r"\.(xls|xlsx|xlsm|csv)(?:\?.*)?$", re.IGNORECASE)
_CATEGORY_RE = re.compile(r"/estadisticas/indice-tematico/[^\"'#?]+/$")


def _is_number(value) -> bool:
    """True para números de Python y de NumPy (los años suelen ser int64)."""
    return pd.api.types.is_number(value)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


class _CategoryParser(HTMLParser):
    """Extrae categorías, secciones y archivos de una página del índice."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.category = ""
        self.section = ""
        self.items: list[dict] = []
        self._anchor: dict | None = None
        self._text: list[str] = []
        self._capturing_span = False

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "span" and "indice-tematico" in (data.get("class") or ""):
            self._capturing_span = True
            self._text = []
        elif tag == "a":
            self._anchor = {"href": data.get("href", ""), "title": data.get("title", "")}
            self._text = []

    def handle_data(self, data):
        if self._anchor is not None or self._capturing_span:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "span" and self._capturing_span:
            self.category = _clean("".join(self._text)) or self.category
            self._capturing_span = False
            self._text = []
        elif tag == "a" and self._anchor is not None:
            text = _clean("".join(self._text))
            href = self._anchor["href"]
            title = _clean(self._anchor["title"])
            if _FILE_RE.search(href):
                self.items.append(
                    {
                        "url": href,
                        "title": text or title,
                        "section": self.section,
                    }
                )
            elif _CATEGORY_RE.search(href) and text:
                self.section = text
            self._anchor = None
            self._text = []


class IneiTematicoAdapter:
    """Adaptador del índice temático del INEI (archivos sin periodo)."""

    institution = "inei_tematico"

    def __init__(self) -> None:
        self._spec = spec_for("inei_tematico")

    # ------------------------------------------------------------------ #
    def _fetch(self, url: str) -> str:
        response = requests.get(url, headers=HEADERS, timeout=120)
        response.raise_for_status()
        return response.text

    def _category_pages(self, html_text: str) -> list[dict]:
        seen: dict[str, bool] = {}
        for href in re.findall(r'href="(/estadisticas/indice-tematico/[^"#?]+/)"', html_text):
            if href.rstrip("/") in (
                "/estadisticas/indice-tematico",
                "/estadisticas/indice-tematico/content/ajax.html",
            ):
                continue
            if href.rstrip("/").endswith("/content/ajax.html"):
                continue
            seen.setdefault(href, True)
        return [
            {"url": "https://www.inei.gob.pe" + href, "name": ""}
            for href in seen
        ]

    def _scan(self) -> dict:
        index_html = self._fetch(INDEX_URL)
        categories = self._category_pages(index_html)
        files: list[dict] = []
        seen_urls: set[str] = set()
        resolved: list[dict] = []
        for category in categories:
            page = self._fetch(category["url"])
            parser = _CategoryParser()
            parser.feed(page)
            name = parser.category or category["url"].rstrip("/").split("/")[-1]
            resolved.append({"name": name, "url": category["url"]})
            for item in parser.items:
                url = item["url"]
                if url.startswith("/"):
                    url = "https://www.inei.gob.pe" + url
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                files.append(
                    {
                        "title": item["title"],
                        "url": url,
                        "section": item["section"],
                        "category": name,
                        "format": item["url"].rsplit(".", 1)[-1].split("?")[0].lower(),
                    }
                )
        return {
            "generated": int(time.time()),
            "categories": resolved,
            "files": files,
        }

    def _load_index(self, force: bool = False) -> dict:
        os.makedirs(CACHE_DIR, exist_ok=True)
        if not force and os.path.exists(INDEX_CACHE):
            try:
                with open(INDEX_CACHE, encoding="utf-8") as handle:
                    cached = json.load(handle)
                if time.time() - cached.get("generated", 0) < _INDEX_TTL:
                    return cached
            except (ValueError, OSError):
                pass
        data = self._scan()
        with open(INDEX_CACHE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return data

    # ------------------------------------------------------------------ #
    def _ensure_indexed(self, force: bool = False) -> int:
        has_rows = catalog.count_prefix("INEI-TEM", "inei_tematico") > 0
        data = self._load_index(force=force or not has_rows)
        if has_rows and not force:
            return 0
        catalog.clear_institution("inei_tematico")
        rows: list[dict] = []
        for item in data.get("files", []):
            url = item.get("url", "")
            if not url:
                continue
            title = _clean(item.get("title", "")) or _clean(url.rsplit("/", 1)[-1])
            code = "INEI-TEM-" + hashlib.sha1(url.encode()).hexdigest()[:10].upper()
            rows.append(
                {
                    "institution": "inei_tematico",
                    "code": code,
                    "category": item.get("category", ""),
                    "group_name": "Índice temático",
                    "name": title,
                    "description": item.get("section", ""),
                    "unit": "",
                    "source": "INEI",
                    "frequency": "Archivo",
                    "pub_group": item.get("section", ""),
                    "area": item.get("category", ""),
                    "start": "",
                    "end": "",
                    "memo": json.dumps(
                        {
                            "kind": "inei_tematico",
                            "url": url,
                            "format": item.get("format", ""),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return catalog.upsert(rows)

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
        scoped["institucion"] = "inei_tematico"
        return metadata.search_catalog(query, filters=scoped, limit=limit)

    def _download(self, url: str) -> str:
        os.makedirs(FILES_DIR, exist_ok=True)
        digest = hashlib.sha1(url.encode()).hexdigest()[:16]
        extension = url.rsplit(".", 1)[-1].split("?")[0].lower() or "bin"
        path = os.path.join(FILES_DIR, f"{digest}.{extension}")
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < _FILE_TTL:
            return path
        response = requests.get(url, headers=HEADERS, timeout=180)
        response.raise_for_status()
        with open(path, "wb") as handle:
            handle.write(response.content)
        return path

    @staticmethod
    def _table(path: str, extension: str) -> pd.DataFrame:
        if extension == "csv":
            frame = pd.read_csv(path, header=None)
        else:
            frame = pd.read_excel(path, sheet_name=0, header=None)
        frame = frame.dropna(how="all", axis=0).dropna(how="all", axis=1)
        if frame.empty:
            return frame
        header_row = None
        for index in range(min(30, len(frame) - 1)):
            values = [value for value in frame.iloc[index].tolist() if pd.notna(value)]
            if len(values) < 2:
                continue
            texts = [value for value in values if isinstance(value, str)]
            numbers = [value for value in values if _is_number(value)]
            following = [
                value
                for value in frame.iloc[index + 1].tolist()
                if _is_number(value)
            ]
            years = all(1900 <= int(number) <= 2100 for number in numbers)
            if following and texts and years:
                header_row = index
                break
        if header_row is None:
            for index in range(min(30, len(frame))):
                values = [
                    value for value in frame.iloc[index].tolist() if pd.notna(value)
                ]
                if len(values) >= 2 and all(
                    isinstance(value, str) for value in values
                ):
                    header_row = index
                    break
        if header_row is None:
            frame.columns = [f"col_{i + 1}" for i in range(frame.shape[1])]
            return frame.reset_index(drop=True)
        headers: list[str] = []
        for column in frame.iloc[header_row]:
            if isinstance(column, float) and column.is_integer():
                text = str(int(column))
            else:
                text = _clean(str(column)) if pd.notna(column) else ""
            headers.append(text or f"col_{len(headers) + 1}")
        seen: dict[str, int] = {}
        unique: list[str] = []
        for header in headers:
            seen[header] = seen.get(header, 0) + 1
            unique.append(header if seen[header] == 1 else f"{header}_{seen[header]}")
        body = frame.iloc[header_row + 1:].copy()
        body.columns = unique
        body = body.dropna(how="all")
        return body.reset_index(drop=True)

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
            url = memo.get("url")
            if not url:
                continue
            extension = memo.get("format") or url.rsplit(".", 1)[-1].lower()
            try:
                path = self._download(url)
                frame = self._table(path, extension)
            except Exception:
                continue
            if frame.empty:
                continue
            if len(codes) > 1:
                frame.insert(0, "archivo", row.get("name", code))
            frames.append(frame)
        if not frames:
            return pd.DataFrame()
        if len(frames) == 1:
            return frames[0]
        return pd.concat(frames, ignore_index=True)

    def info(self, code: str) -> dict:
        row = catalog.get(code) or {}
        return {
            "institution": "inei_tematico",
            "code": code,
            "source": "INEI",
            "url": INDEX_URL,
            "name": row.get("name", ""),
            "updated": time.strftime("%Y-%m-%d"),
        }