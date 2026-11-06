<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/andes_logo_oscuro.svg">
    <img src="assets/andes_logo_claro.svg" alt="ANDES — Open Data Platform" width="360">
  </picture>
</p>

# ANDES — Open Data Platform

**Archivo Nacional de Datos Estadísticos y Sociales**  
**Andean Network for Data, Evidence and Statistics**

ANDES es una plataforma de acceso, integración, exploración y consulta de
estadísticas y datos abiertos. Reduce las barreras de acceso a la información
pública y favorece su uso en investigación, análisis, planificación, docencia y
toma de decisiones.

Integra el catálogo del **Banco Central de Reserva del Perú (BCRP)**, el Portal
de Transparencia del **MEF**, la población proyectada y el índice temático del
**INEI**, y portales estadísticos de entidades públicas del Perú. Incluye
interfaz de escritorio y web (Flet), CLI (Typer) y servidor **MCP** para agentes
de IA.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flet](https://img.shields.io/badge/Flet-1.0.5-7c4dff)
![License](https://img.shields.io/badge/License-GPLv3-blue)
![Brand](https://img.shields.io/badge/ANDES-Open%20Data%20Platform-d8b56d)

## Identidad

- **Nombre**: ANDES.
- **Descriptor**: Open Data Platform.
- **ES**: Archivo Nacional de Datos Estadísticos y Sociales.
- **EN**: Andean Network for Data, Evidence and Statistics.
- **Isotipo**: colibrí de Nasca con flecha de descarga, inspirado en los
  geoglifos y la geometría andina.
- **Temas**: oscuro `#1b293d` / `#d8b56d`; claro `#f1eadc` / `#2a3f48`.
- **Marca**: el uso de la identidad se rige por [`TRADEMARKS.md`](TRADEMARKS.md).
- **Sitios**: desde «Acerca de ANDES» → «Sitios» se listan los 57 portales de
  datos con su nombre completo y enlace, con filtro de búsqueda.

Los datos pertenecen a sus instituciones productoras. ANDES reconoce la fuente,
la metodología, la cobertura y las condiciones de reutilización de cada serie.

## Características

- **Núcleo desacoplado**: `andes.core` maneja metadatos, HTTP y exportación
  sin depender de Flet.
- **GUI** con identidad ANDES, temas claro y oscuro exactos, búsqueda, filtro
  por institución, filtros colapsables, selección múltiple, navegación por
  teclado y tema automático según la hora local con interruptor manual
  persistente.
- **CLI** con `andes search`, `andes download`, `andes download-many`, `andes gui` y
  `andes mcp`.
- **Catálogo local SQLite + FTS5**: búsquedas en milisegundos sin cargar el CSV
  completo de 6,9 MB en cada arranque.
- **Parámetros y detalles por institución**: formatos de periodo propios (BCRP
  `2024-1`; MEF `2026-01`), etiquetas MEF (Rubro, Nivel de gobierno, Programa) y
  descarga vía el adaptador de cada portal.
- **Filtros plegables por institución**: un botón junto al selector de
  institución despliega sus filtros; por defecto quedan en «Todos» y la lista usa
  todo el espacio.
- **Filtro por institución de origen**: selector fuera de los filtros avanzados.
  BCRP muestra frecuencia y filtros propios; MEF (Portal de Transparencia)
  muestra Año, Nivel de gobierno, Rubro, Fuente de financiamiento y Programa,
  con opciones iniciales. La búsqueda MEF indexa bajo demanda los conceptos del
  portal (p. ej. «canon») y luego consulta el catálogo local. La descarga
  histórica recorre cada año disponible (2010–2026) con caché local. En «Todas»
  solo se consulta por palabra clave.
- **Descarga por lotes**: hasta 10 series por petición, una sola sesión HTTP,
  rate-limit y reintentos con backoff para no activar el WAF del portal.
- **Servidor MCP** (stdio) con herramientas `search_series`, `get_metadata` y
  `download_series`.
- **Exportación** a CSV, JSON, XLS, XML, TXT y HTML (XLS binario real).
- **Estadísticas MEF**: 61 cuadros `.xls` convertidos a series anuales y
  trimestrales, además de las transferencias mensuales.
- **INEI Población Proyectada**: 1 892 distritos con proyección 2018–2026,
  una serie por distrito (`INEI-POP-<ubigeo>`), búsqueda por nombre o ubigeo.
  Archivo único: fechas bloqueadas y salida fija en XLS.
- **INEI Temático**: índice temático con 8 categorías y ~826 archivos de datos
  descubiertos en vivo (`INEI-TEM-<hash>`). Archivo único: fechas bloqueadas y
  salida fija en CSV.
- **Portales por institución**: cada portal o servicio estadístico descubierto
  en Gob.pe (1 854 páginas) se atribuye a su institución real (INEI, INPE,
  OSITRAN, etc.) y aparece con ese nombre en el selector. Sin agrupador
  «Gob.pe». Deduplicado por URL y clasificado por plataforma (CSV, Excel, API,
  Tableau, Power BI, PDF, web). Los destinos tabulares se descargan; los
  tableros se abren como enlace externo. Los prefijos repetidos se agrupan
  (Municipalidades, Regiones, UGEL, Redes de Salud) para no inflar el menú.
  Al pasar el puntero por una sigla se muestra un globo con el nombre completo.
- **Detección de documentación PDF** en las descripciones de las series.
- **Caché local** de metadatos y suites de pruebas con mocks.

## Operadores de búsqueda avanzada

El buscador admite operadores booleanos y campos. Las tildes se ignoran.

| Operador | Ejemplo | Resultado |
| --- | --- | --- |
| `AND` (implícito) | `canon AND minero` | ambos términos |
| `OR` | `canon OR forestal` | cualquiera |
| `NOT` / `-` | `canon NOT forestal` · `canon -forestal` | excluye |
| `"frase"` | `"tipo de cambio"` | frase exacta |
| `( )` | `(canon OR regalías) AND minero` | agrupa |
| `campo:` | `codigo:PN00001MM` · `nombre:población` | campo específico |

Campos: `codigo:`, `nombre:`, `grupo:`, `categoria:`, `unidad:`.
Una expresión inválida se reintenta como búsqueda simple por prefijos.

## Requisitos

- Python 3.10 o superior
- Conexión a Internet para la primera descarga de metadatos y para descargar series

## Ejecutables compilados

<!-- DOWNLOADS:START -->
Descarga los archivos de la versión [v1.1.0](https://github.com/EnriqueCastagneda/ANDES/releases/tag/v1.1.0):

| Plataforma | Descarga |
| --- | --- |
| Linux | [bcrp-downloader-linux-1.1.0.tar.gz](https://github.com/EnriqueCastagneda/ANDES/releases/download/v1.1.0/bcrp-downloader-linux-1.1.0.tar.gz) |
| Windows | [bcrp-downloader-windows-1.1.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v1.1.0/bcrp-downloader-windows-1.1.0.zip) |
| macOS | [bcrp-downloader-macos-1.1.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v1.1.0/bcrp-downloader-macos-1.1.0.zip) |
| Android (APK) | [bcrp-downloader-apk-1.1.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v1.1.0/bcrp-downloader-apk-1.1.0.zip) |
| Web | [bcrp-downloader-web-1.1.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v1.1.0/bcrp-downloader-web-1.1.0.zip) |

Consulta la página de [releases](https://github.com/EnriqueCastagneda/ANDES/releases) para descargar otras versiones.
<!-- DOWNLOADS:END -->

> Esta sección se actualiza automáticamente en cada release (`build_release.yml`).

## Instalación

Para usuarios (entorno aislado, recomienda [pipx](https://pipx.pypa.io/)):

```bash
pipx install andes-open-data
```

El paquete de importación es `andes`. Se mantiene el alias `bcrp_downloader`
(``import bcrp_downloader``) y el comando `bcrp` por compatibilidad.

Para desarrollo:

```bash
git clone https://github.com/EnriqueCastagneda/ANDES.git
cd ANDES
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[mcp,dev]"
```

## Uso

### GUI

```bash
andes gui
# o en el navegador:
andes gui --web --port 8550
```

También funciona `python app.py`.

### CLI

```bash
andes search "tipo de cambio" --frequency Mensual --limit 10
andes download PN00001MM --start 2024-1 --end 2024-12 --out datos/pn00001mm.csv
andes download PN00001MM -s 2024-1 -e 2024-12 --format json
andes download-many PN00001MM PN00002MM PN00003MM -s 2024-1 -e 2024-12 -o lote.csv
andes --help
```

### Integración de portales

Cada institución declara su jerarquía y su adaptador nativo. El descubrimiento
usa Chromium local, sin servicios externos. Guía completa:
[`docs/portales.md`](docs/portales.md).

```bash
python scripts/discover_portal.py URL --out fixtures/<portal>/discovered.json
python scripts/export_specs.py
```

### Evaluación de la GUI web

Con la app en marcha en otra terminal:

```bash
andes gui --web --port 8550
python scripts/eval_web_gui.py
```

Requiere Chromium y el extra de desarrollo (`websocket-client`). El script
recorre catálogo, búsqueda, filtros, selección y descarga real, guarda capturas y
`report.json` en `/tmp/opencode/eval-web`, y sale con código 1 si algo falla.

### MCP (Claude Desktop / Cursor)

Instala el extra `mcp` y registra el servidor.

```bash
pipx install "andes-open-data[mcp]"
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "andes": {
      "command": "andes",
      "args": ["mcp"]
    }
  }
}
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "andes": {
      "command": "andes",
      "args": ["mcp"]
    }
  }
}
```

Herramientas expuestas:

| Herramienta | Descripción |
| --- | --- |
| `search_series(query, frequency, category)` | Busca códigos de series |
| `get_metadata(series_code)` | Metadatos y enlace PDF de una serie |
| `download_series(series_code, start_date, end_date, format)` | Descarga y guarda una serie |

### Uso como biblioteca

```python
from andes.core import filter_metadata, load_metadata, download_series_file

df = filter_metadata(load_metadata(), {"frecuencia": "Mensual"})
path = download_series_file("PN00001MM", "2024-1", "2024-12", "csv")
```

## Estructura

```text
andes/
├── andes/
│   ├── core/          # api.py, catalog.py, fetcher.py, metadata.py, portals.py, adapters/, sources.py
│   ├── gui/           # views.py, theme.py
│   ├── cli/           # main.py (Typer)
│   └── mcp/           # server.py
├── tests/             # test_smoke, test_core, test_cli, test_mcp
├── .github/workflows/ # test_and_lint.yml, build_release.yml
├── app.py             # entrypoint compatible con Flet
├── pyproject.toml
├── requirements.txt
└── LICENSE
```

## Pruebas y lint

```bash
pytest -q
ruff check .
```

Las pruebas de red usan mocks; no dependen de la disponibilidad del BCRP.

## CI/CD

- **Test and lint** (`.github/workflows/test_and_lint.yml`): `ruff` y `pytest` en
  Ubuntu, Windows y macOS (Python 3.10 y 3.12) en cada push/PR.
- **Build and release** (`.github/workflows/build_release.yml`): al crear un tag
  `v*`, construye `sdist`/`wheel`, compila binarios con `flet-build-action`
  (Linux, Windows, macOS, APK y Web), publica en PyPI con Trusted Publishing y
  crea el GitHub Release. Configuración: [docs/PUBLISHING.md](docs/PUBLISHING.md).

Publicar una versión:

```bash
git tag -a v2.0.0 -m "ANDES v2.0.0"
git push origin v1.1.3
```

## Datos y API

- Catálogo: <https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata>
- Series: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigo}/{formato}/{inicio}/{fin}/esp`

La información pertenece al Banco Central de Reserva del Perú.

## Identidad y marca

La identidad visual vive en `andes/core/branding.py` y los recursos en
`assets/`. El tema se aplica desde `andes/gui/theme.py` con los
colores institucionales. El código se distribuye bajo GPLv3; la marca se rige
por `TRADEMARKS.md`.

## Licencia

GNU General Public License v3.0. Ver [LICENSE](LICENSE).

```
Copyright (C) 2026 BCRP Downloader contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
```
