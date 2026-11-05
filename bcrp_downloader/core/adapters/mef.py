"""Adaptador nativo del Portal de Transparencia (MEF).

Usa la API pública de Datos Abiertos del MEF (``datastore_search``) directamente,
sin intermediarios. El catálogo MEF crece bajo demanda: al buscar se indexan los
conceptos encontrados en el catálogo local (SQLite) y luego las búsquedas son
locales.
"""

from __future__ import annotations

import hashlib
import json
import re

import pandas as pd
import requests

from .. import catalog
from ..portals import spec_for

DATASTORE = "https://api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/datastore_search"
DETAIL = (
    "https://datosabiertos.mef.gob.pe/Rest/PortalWebRecursoDetalle/v1.0/"
    "getRecursoDetalle"
)
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

    def _resource_id(self) -> str:
        """Id del recurso más reciente de Transferencias."""
        if MefAdapter._resource:
            return MefAdapter._resource
        response = requests.post(
            DETAIL,
            json={"dataset": DATASET, "id_recurso": BOOTSTRAP_RESOURCE},
            headers=HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        resources = response.json().get("resources", [])
        best_id, best_year = BOOTSTRAP_RESOURCE, ""
        for resource in resources:
            name = resource.get("resource_name", "")
            year = _year(name)
            url = resource.get("resource_url", "")
            found = re.search(r"/resource/([a-f0-9-]{36})", url)
            if year and found and year > best_year:
                best_year, best_id = year, found.group(1)
        MefAdapter._resource = best_id
        return best_id

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
            resource_id = meta.get("resource_id")
            recurso = meta.get("recurso")
            if not resource_id or not recurso:
                continue

            collected: list[dict] = []
            offset = 0
            while True:
                records, total = self._records(
                    resource_id,
                    filters={"RECURSO_NOMBRE": recurso},
                    limit=PAGE,
                    offset=offset,
                )
                collected.extend(records)
                offset += len(records)
                if not records or offset >= total:
                    break

            totals: dict[str, float] = {}
            for record in collected:
                year = (record.get("ANO_PRC") or "").strip()
                month = (record.get("MES_PRC") or "").strip()
                amount = record.get("MONTO_AUTORIZADO") or record.get("MONTO_ACREDITADO")
                if not year or not month or amount in (None, ""):
                    continue
                key = f"{int(year):04d}-{int(month):02d}-01"
                try:
                    totals[key] = totals.get(key, 0.0) + float(amount)
                except (TypeError, ValueError):
                    continue
            if totals:
                low, high = _bounds(start, end)
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
