"""Contrato declarativo de portales y registro de adaptadores nativos.

Cada institución declara su jerarquía de datos una sola vez. La GUI, el CLI y
los adaptadores leen ese contrato; agregar un portal nuevo no toca la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import sources


@dataclass(frozen=True)
class Dimension:
    """Dimensión/filtro de un portal.

    ``key`` es la clave que entiende ``catalog.search``; ``kind`` distingue un
    desplegable de un rango de fechas o de la frecuencia.
    """

    key: str
    label: str
    kind: str = "select"  # select | date_range | frequency
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortalSpec:
    """Especificación mínima para integrar un portal de forma nativa."""

    id: str
    name: str
    short_name: str
    base_url: str
    metadata_url: str = ""
    endpoints: dict[str, str] = field(default_factory=dict)
    period_format: str = ""
    pagination: str = ""
    dimensions: tuple[Dimension, ...] = ()
    pending: tuple[str, ...] = ()


def _dim(key: str, label: str, kind: str = "select") -> Dimension:
    return Dimension(key=key, label=label, kind=kind)


# Jerarquía de cada portal, en orden de presentación.
_DIMENSIONS: dict[str, tuple[Dimension, ...]] = {
    "bcrp": (
        _dim("frecuencia", "Frecuencia", "frequency"),
        _dim("area", "Área que publica"),
        _dim("fuente", "Fuente"),
        _dim("categoria", "Categoría de serie"),
        _dim("grupo_serie", "Grupo de serie"),
        _dim("creacion", "Rango de creación", "date_range"),
        _dim("actualizacion", "Rango de actualización", "date_range"),
    ),
    "mef": (
        _dim("inicio", "Año"),
        _dim("grupo_serie", "Nivel de gobierno"),
        _dim("categoria", "Rubro"),
        _dim("fuente", "Fuente de financiamiento"),
        _dim("grupo_publicacion", "Programa"),
    ),
    "inei": (
        _dim("area", "Departamento"),
    ),
}

_ENDPOINTS: dict[str, dict[str, str]] = {
    "bcrp": {
        "catalog": "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata",
        "series": "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codes}/json/{start}/{end}/esp",
    },
    "mef": {
        "portal": "https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx",
    },
}

_PERIODS = {"bcrp": "2026-11, 2026-4, 2026, 2026-11-5", "mef": "2026"}
_PENDING = {"bcrp": (), "mef": ()}

# Clave de filtro de la GUI -> columna/campo del catálogo.
_SEED_KEYS = {
    "inicio": "start",
    "fin": "end",
    "grupo_serie": "group_name",
    "categoria": "category",
    "fuente": "source",
    "grupo_publicacion": "pub_group",
    "area": "area",
}


def spec_for(source_id: str) -> PortalSpec:
    """Devuelve la especificación de un portal registrado."""
    source = sources.get_source(source_id)
    if source is None:
        raise ValueError(f"Portal no registrado: {source_id}")
    dimensions = _DIMENSIONS.get(source.id, ())
    if source.filter_options:
        dimensions = tuple(
            Dimension(
                key=dimension.key,
                label=dimension.label,
                kind=dimension.kind,
                options=source.filter_options.get(
                    _SEED_KEYS.get(dimension.key, dimension.key), dimension.options
                ),
            )
            for dimension in dimensions
        )
    return PortalSpec(
        id=source.id,
        name=source.name,
        short_name=source.short_name,
        base_url=source.base_url,
        metadata_url=source.metadata_url,
        endpoints=_ENDPOINTS.get(source.id, {}),
        period_format=_PERIODS.get(source.id, ""),
        pagination="lotes de 10 series" if source.id == "bcrp" else "",
        dimensions=dimensions,
        pending=_PENDING.get(source.id, ()),
    )


def specs() -> list[PortalSpec]:
    """Especificaciones de todas las instituciones habilitadas."""
    return [spec_for(source.id) for source in sources.sources()]


def catalog_field(key: str) -> str:
    """Campo del catálogo asociado a una clave de filtro de la GUI."""
    return _SEED_KEYS.get(key, key)


def dimension_options(source_id: str, key: str) -> tuple[str, ...]:
    """Opciones declaradas para una dimensión (sin consultar el catálogo)."""
    for dimension in spec_for(source_id).dimensions:
        if dimension.key == key:
            return dimension.options
    return ()
