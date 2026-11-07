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

![CI](https://github.com/EnriqueCastagneda/ANDES/actions/workflows/test_and_lint.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flet](https://img.shields.io/badge/Flet-1.0.5-7c4dff)
![License](https://img.shields.io/badge/License-GPLv3-blue)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS%20%7C%20Android%20%7C%20Web-informational)
![Brand](https://img.shields.io/badge/ANDES-Open%20Data%20Platform-d8b56d)

## Identidad

- **Nombre**: ANDES.
- **Descriptor**: Open Data Platform.
- **ES**: Archivo Nacional de Datos Estadísticos y Sociales.
- **EN**: Andean Network for Data, Evidence and Statistics.
- **Isotipo**: colibrí de Nasca con flecha de descarga, inspirado en los
  geoglifos y la geometría andina.
- **Icono**: `assets/icon/` (16–1024 px, `.ico`, `.icns`, `.svg`); favicon y
  iconos PWA en `assets/favicon.png` y `assets/icons/`. El icono sustituye a la
  animación de carga de Flet mediante `assets/icons/loading-animation.png`.
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
- **Origen en detalles**: enlace al recurso y etiqueta de API (BCRP, MEF,
  INEI, portal) con tooltip.
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
Descarga los archivos de la versión [v2.0.0](https://github.com/EnriqueCastagneda/ANDES/releases/tag/v2.0.0):

| Plataforma | Descarga |
| --- | --- |
| Linux | [andes-linux-2.0.0.tar.gz](https://github.com/EnriqueCastagneda/ANDES/releases/download/v2.0.0/andes-linux-2.0.0.tar.gz) |
| Windows | [andes-windows-2.0.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v2.0.0/andes-windows-2.0.0.zip) |
| macOS | [andes-macos-2.0.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v2.0.0/andes-macos-2.0.0.zip) |
| Android (APK) | [andes-apk-2.0.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v2.0.0/andes-apk-2.0.0.zip) |
| Web | [andes-web-2.0.0.zip](https://github.com/EnriqueCastagneda/ANDES/releases/download/v2.0.0/andes-web-2.0.0.zip) |

Consulta la página de [releases](https://github.com/EnriqueCastagneda/ANDES/releases) para descargar otras versiones.
<!-- DOWNLOADS:END -->

> Esta sección se actualiza automáticamente en cada release (`build_release.yml`).

## Instalación

Para usuarios (entorno aislado, recomienda [pipx](https://pipx.pypa.io/)):

```bash
pipx install andes-open-data
```


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

### Menú de aplicación

En la cabecera del panel derecho, junto a la campana:

- **Tema**: alterna claro/oscuro.
- **Menú** (☰):
  - **Carpeta de guardado**: se define en la primera descarga y puede cambiarse
    con el desplegable o con «Otra carpeta…». La ruta se normaliza (`~`,
    variables de entorno), se crea si falta y se comprueba que admita escritura
    antes de guardarla.
  - **Reiniciar** (`Ctrl+R` en escritorio; recarga en web).
  - **Acerca de ANDES**.
  - **Salir** (`Ctrl+Q` en escritorio).
- `Escape` cierra el menú.

Los navegadores pueden interceptar `Ctrl+R`/`Ctrl+Q`; en web usa los botones.

### Rutas de datos y configuración

Orden de prioridad:

1. `ANDES_DATA_DIR` y `ANDES_CONFIG_DIR` (variables de entorno).
2. `FLET_APP_STORAGE_DATA` en apps empaquetadas con Flet.
3. Directorio del usuario si el ejecutable está congelado:
   - Linux: `$XDG_DATA_HOME/andes` y `$XDG_CONFIG_HOME/andes`
     (`~/.local/share/andes`, `~/.config/andes`).
   - macOS: `~/Library/Application Support/andes`.
   - Windows: `%LOCALAPPDATA%\ANDES` y `%APPDATA%\ANDES`.
4. Desarrollo desde el repositorio: `data/`.

Las preferencias (`prefs.json`) se escriben de forma atómica. La carpeta de
guardado se valida y se prueba con un archivo temporal; si una ruta guardada
deja de existir o no admite escritura, se usa la predeterminada y se avisa.

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
ANDES/
├── andes/
│   ├── core/          # api, catalog, fetcher, metadata, portals, adapters, branding
│   ├── gui/           # views.py, theme.py
│   ├── cli/           # main.py (Typer)
│   └── mcp/           # server.py
├── assets/            # logotipo, isotipo, iconos
├── docs/              # identidad, portales, publicación
├── fixtures/          # contratos de portales
├── scripts/           # descubrimiento, eval web, pruebas
├── tests/
├── app.py             # entrypoint Flet
├── pyproject.toml
├── TRADEMARKS.md
├── CITATION.cff
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Pruebas y lint

```bash
pytest -q
ruff check .
```

Las pruebas de red usan mocks; no dependen de la disponibilidad de las
fuentes externas.

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
git push origin v2.0.0
```

## Fuentes de datos

| Fuente | Contenido | Enlace |
| --- | --- | --- |
| BCRP | Catálogo y series monetarias, cambiarias y macroeconómicas | <https://estadisticas.bcrp.gob.pe> |
| MEF | Transferencias y cuadros estadísticos | <https://datosabiertos.mef.gob.pe> |
| INEI | Población proyectada por distrito e índice temático | <https://www.inei.gob.pe/estadisticas-indice-tematico/> |
| Gob.pe | 125 portales y servicios estadísticos de 53 entidades | <https://www.gob.pe/busquedas?term=estadisticas> |

Los datos pertenecen a sus instituciones productoras. ANDES reconoce fuente,
metodología, cobertura, periodo y condiciones de reutilización. No se atribuye
su propiedad intelectual.

## Identidad y marca

La identidad visual vive en `andes/core/branding.py` y los recursos en
`assets/`. El tema se aplica desde `andes/gui/theme.py` con los
colores institucionales. El código se distribuye bajo GPLv3; la marca se rige
por `TRADEMARKS.md`.

## Citación

Si usas ANDES en investigación o docencia, cita el proyecto. Los metadatos están
en [`CITATION.cff`](CITATION.cff):

```bibtex
@software{andes2026,
  title  = {ANDES — Open Data Platform},
  author = {Castañeda, Enrique},
  year   = {2026},
  url    = {https://github.com/EnriqueCastagneda/ANDES},
  license = {GPL-3.0-or-later}
}
```

## Seguridad

Reporta vulnerabilidades de forma privada según [`SECURITY.md`](SECURITY.md).
No abras issues públicos con detalles explotables.

## Contribuir

Lee [`CONTRIBUTING.md`](CONTRIBUTING.md) y el
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Los cambios se registran en
[`CHANGELOG.md`](CHANGELOG.md).

## Licencia

GNU General Public License v3.0. Ver [LICENSE](LICENSE).

```
Copyright (C) 2026 ANDES contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
```
