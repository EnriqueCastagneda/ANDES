# BCRP Downloader

Aplicación modular en Python para explorar el catálogo de series estadísticas del
**Banco Central de Reserva del Perú (BCRP)** y descargar sus series temporales.
Incluye interfaz de escritorio (Flet), CLI (Typer) y servidor **MCP** para agentes
de IA.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flet](https://img.shields.io/badge/Flet-1.0.5-7c4dff)
![License](https://img.shields.io/badge/License-GPLv3-blue)

## Características

- **Núcleo desacoplado**: `bcrp_downloader.core` maneja metadatos, HTTP y exportación
  sin depender de Flet.
- **GUI** oscura tipo SaaS con búsqueda, filtro por frecuencia, filtros avanzados
  colapsables, selección múltiple, navegación por teclado y tema automático según
  la hora local (claro 06:00–17:59, oscuro 18:00–05:59) con interruptor manual.
- **CLI** con `bcrp search`, `bcrp download`, `bcrp gui` y `bcrp mcp`.
- **Servidor MCP** (stdio) con herramientas `search_series`, `get_metadata` y
  `download_series`.
- **Exportación** a CSV, JSON, XLS, XML, TXT y HTML.
- **Detección de documentación PDF** en las descripciones de las series.
- **Caché local** de metadatos y suites de pruebas con mocks.

## Requisitos

- Python 3.10 o superior
- Conexión a Internet para la primera descarga de metadatos y para descargar series

## Instalación

Para usuarios (entorno aislado, recomienda [pipx](https://pipx.pypa.io/)):

```bash
pipx install bcrp-downloader
```

Para desarrollo:

```bash
git clone https://github.com/EnriqueCastagneda/BCRP-Downloader.git
cd BCRP-Downloader
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[mcp,dev]"
```

## Uso

### GUI

```bash
bcrp gui
# o en el navegador:
bcrp gui --web --port 8550
```

También funciona `python app.py`.

### CLI

```bash
bcrp search "tipo de cambio" --frequency Mensual --limit 10
bcrp download PN00001MM --start 2024-1 --end 2024-12 --out datos/pn00001mm.csv
bcrp download PN00001MM -s 2024-1 -e 2024-12 --format json
bcrp --help
```

### MCP (Claude Desktop / Cursor)

Instala el extra `mcp` y registra el servidor.

```bash
pipx install "bcrp-downloader[mcp]"
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bcrp-downloader": {
      "command": "bcrp",
      "args": ["mcp"]
    }
  }
}
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "bcrp-downloader": {
      "command": "bcrp",
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
from bcrp_downloader.core import filter_metadata, load_metadata, download_series_file

df = filter_metadata(load_metadata(), {"frecuencia": "Mensual"})
path = download_series_file("PN00001MM", "2024-1", "2024-12", "csv")
```

## Estructura

```text
bcrp_downloader/
├── bcrp_downloader/
│   ├── core/          # api.py, metadata.py, http.py, paths.py
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
  (Linux, Windows, macOS, APK y Web), publica en PyPI (si existe
  `PYPI_API_TOKEN`) y crea el GitHub Release.

Publicar una versión:

```bash
git tag -a v1.1.0 -m "BCRP Downloader v1.1.0"
git push origin v1.1.0
```

## Datos y API

- Catálogo: <https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata>
- Series: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigo}/{formato}/{inicio}/{fin}/esp`

La información pertenece al Banco Central de Reserva del Perú.

## Licencia

GNU General Public License v3.0. Ver [LICENSE](LICENSE).

```
Copyright (C) 2026 BCRP Downloader contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
```
