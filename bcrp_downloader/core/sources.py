"""Registro de instituciones de origen de los datos.

Cada fuente añadida al explorador se declara aquí. El catálogo guarda el
``id`` de la institución y la GUI construye su filtro desde este registro.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    """Institución que publica una familia de series."""

    id: str
    name: str
    short_name: str
    base_url: str
    metadata_url: str = ""
    enabled: bool = True
    # Valores iniciales de los filtros propios (se completan con el catálogo).
    filter_options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Archivo único: no hay rango de fechas ni periodos que elegir.
    fixed_period: bool = False
    # Formatos de salida permitidos; vacío = todos. Si queda uno, la GUI lo fija.
    formats: tuple[str, ...] = ()


_BASE_SOURCES: tuple[Source, ...] = (
    Source(
        id="bcrp",
        name="Banco Central de Reserva del Perú",
        short_name="BCRP",
        base_url="https://estadisticas.bcrp.gob.pe",
        metadata_url="https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata",
    ),
    Source(
        id="mef",
        name="Ministerio de Economía y Finanzas - Portal de Transparencia",
        short_name="MEF",
        base_url="https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx",
        metadata_url="",
        filter_options={
            "start": tuple(str(year) for year in range(1999, 2027)),
            "group_name": (
                "Gobierno Nacional",
                "Gobiernos Regionales",
                "Gobiernos Locales",
            ),
            "category": (
                "Personal y Obligaciones Sociales",
                "Obligaciones Previsionales",
                "Bienes y Servicios",
                "Transferencias",
                "Otros Gastos",
                "Adquisición de Activos no Financieros",
                "Servicio de la Deuda",
                "Donaciones y Transferencias",
            ),
            "source": (
                "Recursos Ordinarios",
                "Recursos Directamente Recaudados",
                "Recursos por Operaciones Oficiales de Crédito",
                "Donaciones y Transferencias",
                "Recursos Determinados",
            ),
            "pub_group": (
                "Programas Presupuestales",
                "Acciones Centrales",
                "Asignaciones Presupuestarias que no resultan en Productos",
            ),
        },
    ),
    Source(
        id="inei",
        name="Instituto Nacional de Estadística e Informática - Población proyectada",
        short_name="INEI Población Proyectada",
        base_url="https://www.gob.pe/institucion/inei",
        metadata_url=(
            "https://www.gob.pe/institucion/inei/"
            "informes-publicaciones/6894980-peru-poblacion-total-proyectada-al-30-"
            "de-junio-de-cada-ano-segun-departamento-provincia-y-distrito-2018-2026"
        ),
        filter_options={
            "start": tuple(str(year) for year in range(2018, 2027)),
        },
        fixed_period=True,
        formats=("xls",),
    ),
    Source(
        id="inei_tematico",
        name="Instituto Nacional de Estadística e Informática - Índice temático",
        short_name="INEI Temático",
        base_url="https://www.inei.gob.pe/estadisticas-indice-tematico/",
        metadata_url="https://www.inei.gob.pe/estadisticas-indice-tematico/",
        fixed_period=True,
        formats=("csv",),
    ),
)


def _portal_sources() -> tuple[Source, ...]:
    """Una institución por cada entidad con portales en el registro Gob.pe."""
    from . import gobpe

    generated: list[Source] = []
    for inst in gobpe.institutions():
        generated.append(
            Source(
                id=f"gobpe:{inst['id']}",
                name=inst.get("name") or inst["label"],
                short_name=inst["label"],
                base_url="https://www.gob.pe/",
                metadata_url="https://www.gob.pe/busquedas.json?term=estadisticas",
                fixed_period=True,
                formats=("csv",),
            )
        )
    return tuple(generated)


SOURCES: tuple[Source, ...] = _BASE_SOURCES + _portal_sources()

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


def declared() -> list[Source]:
    """Solo las instituciones base (sin los portales generados)."""
    return list(_BASE_SOURCES)


def labels() -> dict[str, str]:
    """Mapa ``id`` -> nombre corto, para desplegables."""
    return {source.id: source.short_name for source in sources()}
