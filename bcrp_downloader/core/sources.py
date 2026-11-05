"""Registro de instituciones de origen de los datos.

Cada fuente añadida al explorador se declara aquí. El catálogo guarda el
``id`` de la institución y la GUI construye su filtro desde este registro.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    """Institución que publica una familia de series."""

    id: str
    name: str
    short_name: str
    base_url: str
    metadata_url: str = ""
    enabled: bool = True


SOURCES: tuple[Source, ...] = (
    Source(
        id="bcrp",
        name="Banco Central de Reserva del Perú",
        short_name="BCRP",
        base_url="https://estadisticas.bcrp.gob.pe",
        metadata_url="https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata",
    ),
)

DEFAULT_SOURCE = "bcrp"

_BY_ID = {source.id: source for source in SOURCES}


def get_source(source_id: str | None) -> Source | None:
    """Devuelve la institución por id (sin distinguir mayúsculas)."""
    if not source_id:
        return None
    return _BY_ID.get(source_id.strip().lower())


def sources(enabled_only: bool = True) -> list[Source]:
    """Lista las instituciones registradas."""
    return [s for s in SOURCES if s.enabled or not enabled_only]


def labels() -> dict[str, str]:
    """Mapa ``id`` -> nombre corto, para desplegables."""
    return {source.id: source.short_name for source in sources()}
