"""Adaptador nativo del Portal de Transparencia (MEF).

La jerarquía y las opciones ya están declaradas; la descarga queda pendiente
hasta conectar el endpoint de datos del portal. No usa servicios externos en
tiempo de ejecución.
"""

from __future__ import annotations

import pandas as pd

from .. import catalog
from ..portals import spec_for


class MefAdapter:
    spec = spec_for("mef")

    def search(self, query: str, *, filters: dict | None = None,
               limit: int | None = 100, offset: int = 0) -> pd.DataFrame:
        # Sin series MEF cargadas todavía: se devuelve un marco vacío con el
        # mismo contrato de columnas que BCRP.
        return pd.DataFrame(columns=list(catalog.COLUMNS.values()))

    def fetch(self, codes: list[str], start: str, end: str,
              frequency: str | None = None) -> pd.DataFrame:
        raise NotImplementedError(
            "MEF: falta conectar el endpoint de datos del Portal de Transparencia"
        )

    def pending(self) -> tuple[str, ...]:
        return self.spec.pending
