"""Adaptador nativo del Portal de Transparencia (MEF).

Usa la API pública de Datos Abiertos del MEF (``datastore_search``) directamente,
sin intermediarios. El catálogo MEF crece bajo demanda: al buscar se indexan los
conceptos encontrados en el catálogo local (SQLite) y luego las búsquedas son
locales.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from urllib.parse import urlencode

import pandas as pd
import requests

from .. import catalog
from ..paths import DATA_DIR
from ..portals import spec_for

DATASTORE = "https://api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/datastore_search"
DETAIL = (
    "https://datosabiertos.mef.gob.pe/Rest/PortalWebRecursoDetalle/v1.0/"
    "getRecursoDetalle"
)
DUMP = "https://api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/dump"
DATASET = "transferencias-de-fondos-y-asignaciones-financieras"
BOOTSTRAP_RESOURCE = "fab56aea-30af-4b41-9eda-b968b87c7171"  # 2022
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
PAGE = 10000
CACHE_DIR = os.path.join(DATA_DIR, "mef")


def _code(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12].upper()
    return f"MEF-{digest}"


def _year(name: str) -> str:
    match = re.search(r"(19|20)\d{2}", name or "")
    return match.group(0) if match else ""


def _bounds(start: str, end: str) -> tuple[str, str]:
    """Normaliza un rango de periodos MEF (YYYY o YYYY-MM) a YYYY-MM."""

    def norm(value: str, last: bool) -> str:
        value = (value or "").strip()
        if re.fullmatch(r"\d{4}", value):
            return f"{value}-12" if last else f"{value}-01"
        match = re.match(r"(\d{4})-(\d{1,2})", value)
        if match:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
        return "0000-01" if not last else "9999-12"

    return norm(start, False), norm(end, True)


class MefAdapter:
    spec = spec_for("mef")
    _resource: str | None = None
    _resources: dict[str, str] | None = None

    def _resource_map(self) -> dict[str, str]:
        """Mapa año -> id de recurso de Transferencias."""
        if MefAdapter._resources:
            return MefAdapter._resources
        response = requests.post(
            DETAIL,
            json={"dataset": DATASET, "id_recurso": BOOTSTRAP_RESOURCE},
            headers=HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        mapping: dict[str, str] = {}
        for resource in response.json().get("resources", []):
            year = _year(resource.get("resource_name", ""))
            found = re.search(
                r"/resource/([a-f0-9-]{36})", resource.get("resource_url", "")
            )
            if year and found:
                mapping[year] = found.group(1)
        mapping.setdefault("2022", BOOTSTRAP_RESOURCE)
        MefAdapter._resources = mapping
        return mapping

    def _resource_id(self) -> str:
        """Id del recurso más reciente de Transferencias."""
        if MefAdapter._resource:
            return MefAdapter._resource
        mapping = self._resource_map()
        MefAdapter._resource = mapping[max(mapping)]
        return MefAdapter._resource

    def _records(self, resource_id: str, *, q: str | None = None,
                 filters: dict | None = None, limit: int = PAGE,
                 offset: int = 0) -> tuple[list[dict], int]:
        params: dict = {
            "resource_id": resource_id,
            "limit": limit,
            "offset": offset,
        }
        if q:
            params["q"] = q
        if filters:
            params["filters"] = json.dumps(filters, ensure_ascii=False)
        response = requests.get(DATASTORE, params=params, headers=HEADERS, timeout=90)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("records") or []
        total = int(payload.get("result", {}).get("include_total") or len(records))
        return records, total

    def _dump(self, resource_id: str, recurso: str, year: str = "") -> str:
        """CSV filtrado del MEF, con caché local y sondeo corto."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        digest = hashlib.sha1(
            f"{resource_id}|{recurso}".encode()
        ).hexdigest()[:16]
        cache_path = os.path.join(CACHE_DIR, f"{digest}.csv")
        ttl = 86400 if year == str(time.localtime().tm_year) else 30 * 86400
        if os.path.exists(cache_path) and time.time() - os.path.getmtime(
            cache_path
        ) < ttl:
            with open(cache_path, encoding="utf-8-sig") as handle:
                return handle.read()

        query = urlencode(
            {
                "id": resource_id,
                "filters": json.dumps(
                    {"RECURSO_NOMBRE": recurso}, ensure_ascii=False
                ),
            }
        )
        url = f"{DUMP}?{query}"
        for _ in range(20):
            response = requests.get(url, headers=HEADERS, timeout=180)
            response.raise_for_status()
            text = response.text.lstrip("\ufeff").lstrip()
            if text.startswith('"ANO_PRC"') or text.startswith("ANO_PRC"):
                with open(cache_path, "w", encoding="utf-8") as handle:
                    handle.write(text)
                return text
            time.sleep(1.5)
        raise RuntimeError("MEF no devolvió el CSV filtrado")

    def _monthly_totals(
        self, resource_id: str, recurso: str, year: str = ""
    ) -> dict[str, float]:
        text = self._dump(resource_id, recurso, year)
        frame = pd.read_csv(io.StringIO(text))
        if "MONTO_AUTORIZADO" not in frame.columns:
            return {}
        amounts = pd.to_numeric(
            frame["MONTO_AUTORIZADO"].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        ).fillna(0.0)
        frame = frame.assign(_monto=amounts)
        frame = frame[
            frame["ANO_PRC"].notna() & frame["MES_PRC"].notna()
        ].copy()
        frame["_key"] = (
            frame["ANO_PRC"].astype(int).map("{:04d}".format)
            + "-"
            + frame["MES_PRC"].astype(int).map("{:02d}".format)
            + "-01"
        )
        return frame.groupby("_key")["_monto"].sum().to_dict()

    def _ingest(self, query: str) -> int:
        resource_id = self._resource_id()
        records, _ = self._records(resource_id, q=query, limit=2000)
        needle = query.lower()
        concepts: dict[str, dict] = {}
        for record in records:
            resource = (record.get("RECURSO_NOMBRE") or "").strip()
            rubro = (record.get("RUBRO_NOMBRE") or "").strip()
            if not resource:
                continue
            if needle not in resource.lower() and needle not in rubro.lower():
                continue
            concepts.setdefault(
                resource,
                {
                    "rubro": rubro,
                    "nivel": (record.get("TIPO_ENTIDAD_NOMBRE") or "").strip(),
                    "programa": (record.get("GRUPO_TRANSFERENCIA_NOMBRE") or "").strip(),
                    "fuente": (record.get("FUENTE_NOMBRE") or "").strip(),
                    "year": (record.get("ANO_PRC") or "").strip(),
                },
            )
        if not concepts:
            return 0

        months = [
            int(record.get("MES_PRC"))
            for record in records
            if (record.get("MES_PRC") or "").isdigit()
        ]
        first_month = min(months) if months else 1
        last_month = max(months) if months else 12
        rows = []
        for resource, meta in concepts.items():
            year = meta["year"] or _year(resource)
            start = f"{int(year):04d}-{first_month:02d}"
            end = f"{int(year):04d}-{last_month:02d}"
            rows.append(
                {
                    "institution": "mef",
                    "code": _code(resource),
                    "category": meta["rubro"],
                    "group_name": meta["nivel"],
                    "name": f"{resource} ({meta['rubro']})" if meta["rubro"] else resource,
                    "description": "Transferencias de fondos y asignaciones financieras",
                    "unit": "S/",
                    "source": "MEF",
                    "frequency": "Mensual",
                    "pub_group": meta["programa"],
                    "area": meta["fuente"],
                    "start": start,
                    "end": end,
                    "memo": json.dumps(
                        {"resource_id": resource_id, "recurso": resource, "year": year},
                        ensure_ascii=False,
                    ),
                }
            )
        return catalog.upsert(rows)

    def search(self, query: str, *, filters: dict | None = None,
               limit: int | None = 100, offset: int = 0) -> pd.DataFrame:
        from .. import metadata

        scoped = dict(filters or {})
        scoped["institucion"] = "mef"
        frame = metadata.search_catalog(
            query, filters=scoped, limit=limit, offset=offset
        )
        legacy_periods = not frame.empty and all(
            len(str(value)) == 4 for value in frame["Fecha de inicio"]
        )
        if query.strip() and (frame.empty or legacy_periods):
            if self._ingest(query.strip()):
                frame = metadata.search_catalog(
                    query, filters=scoped, limit=limit, offset=offset
                )
        return frame

    def fetch(self, codes: list[str], start: str, end: str,
              frequency: str | None = None) -> pd.DataFrame:
        frames = []
        for code in codes:
            row = catalog.get(code)
            if not row or not row.get("memo"):
                continue
            try:
                meta = json.loads(row["memo"])
            except ValueError:
                continue
            recurso = meta.get("recurso")
            if not recurso:
                continue
            low, high = _bounds(start, end)
            mapping = self._resource_map()
            totals: dict[str, float] = {}
            for year in range(int(low[:4]), int(high[:4]) + 1):
                resource_id = mapping.get(str(year))
                if not resource_id:
                    continue
                totals.update(
                    self._monthly_totals(resource_id, recurso, str(year))
                )

            if totals:
                ordered = [
                    key for key in sorted(totals)
                    if low[:7] <= key[:7] <= high[:7]
                ]
                if ordered:
                    frames.append(
                        pd.DataFrame(
                            {
                                "fecha": ordered,
                                code.upper(): [totals[key] for key in ordered],
                            }
                        )
                    )

        if not frames:
            return pd.DataFrame(columns=["fecha"])
        out = frames[0]
        for extra in frames[1:]:
            out = out.merge(extra, on="fecha", how="outer")
        return out.sort_values("fecha").reset_index(drop=True)

    def pending(self) -> tuple[str, ...]:
        return self.spec.pending
