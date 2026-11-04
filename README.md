# BCRP Downloader

Aplicación de escritorio minimalista, escrita en Python con [Flet](https://flet.dev/),
para explorar el catálogo de series estadísticas del **Banco Central de Reserva del
Perú (BCRP)** y descargar sus series temporales.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flet](https://img.shields.io/badge/Flet-1.0.5-7c4dff)
![License](https://img.shields.io/badge/License-GPLv3-blue)

## Descripción

BCRP Downloader descarga el catálogo oficial de metadatos (`17.000+` series),
lo indexa localmente con Pandas y permite buscar, filtrar y visualizar cada serie.
Desde la propia interfaz se consulta la API pública del BCRP y se exporta la serie
en el formato elegido.

## Características

- **Catálogo local con caché**: descarga los metadatos una sola vez y los reutiliza.
- **Búsqueda global** por código o nombre, con sugerencias.
- **Filtro rápido por frecuencia**: Todos, Diaria, Mensual, Trimestral y Anual.
- **Filtros avanzados colapsables**: área que publica, fuente, categoría, grupo y
  rangos de fecha de creación/actualización.
- **Selección múltiple** de series y **descarga por lote**.
- **Navegación por teclado**: `↑` / `↓` para mover el foco, `Enter` / `Espacio`
  para seleccionar.
- **Formatos de descarga**: CSV, JSON, XLS, XML, TXT y HTML.
- **Inspector de metadatos** en formato clave-valor, con detección de enlaces a
  documentación PDF.
- **Diseño oscuro** tipo SaaS/Bento, totalmente adaptativo al tamaño de la ventana.

## Requisitos

- Python 3.10 o superior
- Linux, macOS o Windows (modo escritorio de Flet)
- Conexión a Internet para la primera descarga de metadatos y para descargar series

## Instalación

```bash
git clone <URL-del-repositorio>
cd bcrp-downloader

python3 -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Ejecución

```bash
python app.py
```

Si el cliente de escritorio de Flet no está disponible, se puede ejecutar en modo
navegador:

```bash
python -c "import flet as ft, app; ft.run(app.main, port=8550, view=ft.AppView.WEB_BROWSER)"
```

## Uso

1. Al iniciar, la aplicación descarga `data/metadata_bcrp.csv` si no existe.
2. Escribe en la barra de búsqueda para filtrar por código o nombre.
3. Usa las píldoras de frecuencia y/o **Filtros Avanzados ⚙️** para refinar.
4. Haz clic en una serie para ver sus metadatos; usa el checkbox para seleccionar
   varias o navega con el teclado.
5. Define el rango de fechas y el formato de salida.
6. Pulsa **Descargar**: se guarda una o varias series en `outputs/`.

## Estructura del proyecto

```text
bcrp-downloader/
├── app.py                 # Aplicación monolítica (UI + lógica)
├── requirements.txt       # Dependencias
├── README.md              # Este documento
├── LICENSE                # GNU GPL v3
├── CONTRIBUTING.md        # Guía de contribución
├── pyproject.toml         # Metadatos y configuración de build (Flet)
├── .github/workflows/     # CI y publicación de releases
├── data/                  # Caché de metadatos (generado, no versionado)
├── outputs/               # Archivos descargados (generado, no versionado)
└── tests/                 # Pruebas con pytest
```

## Pruebas

```bash
python -m pytest -q
```

Las pruebas de red se omiten automáticamente cuando la CDN del BCRP devuelve una
página de bloqueo temporal.

## Integración continua (GitHub Actions)

El repositorio incluye dos flujos en `.github/workflows/`:

- **CI** (`.github/workflows/ci.yml`): se ejecuta en cada `push` a `main`/`master`,
  en cada *pull request* y manualmente. Instala dependencias, compila `app.py` y
  ejecuta `pytest` en Python 3.10 y 3.12.
- **Build** (`.github/workflows/build.yml`): usa
  [`flet-dev/flet-build-action`](https://github.com/flet-dev/flet-build-action)
  para compilar la aplicación en los cinco destinos configurados y publicar los
  artefactos.

### Configuración del build

| Pregunta | Respuesta en este repositorio |
| --- | --- |
| Archivo principal | `app.py` en la raíz (estructura propia, declarada con `[tool.flet.app] module = "app"`) |
| Gestor de dependencias | `pip` + `requirements.txt` para desarrollo; `pyproject.toml` para el build |
| Plataformas | Linux, Windows, macOS, Android (APK) y Web. iOS no está incluido |
| Publicación | Automática al crear un tag `v*` y manual desde *workflow_dispatch* (`publish_release`) |

La matriz de `.github/workflows/build.yml` compila:

| Destino | Runner | Artefacto |
| --- | --- | --- |
| `linux` | `ubuntu-latest` | tar.gz |
| `windows` | `windows-latest` | zip |
| `macos` | `macos-latest` | zip |
| `apk` | `ubuntu-latest` | APK de Android |
| `web` | `ubuntu-latest` | zip |

### Publicar una versión

Automático, al empujar un tag:

```bash
git tag -a v1.0.1 -m "BCRP Downloader v1.0.1"
git push origin v1.0.1
```

Manual, desde *Actions → Build → Run workflow*, activando `publish_release` e
indicando `release_tag` (por ejemplo `v1.0.1`). Si solo se quieren los artefactos,
deja `publish_release` desactivado y descárgalos desde la ejecución.



## Datos y API

- Catálogo: <https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata>
- Series: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigo}/{formato}/{inicio}/{fin}/esp`

La información pertenece al Banco Central de Reserva del Perú. Esta herramienta
solo facilita su consulta y exportación.

## Licencia

Este proyecto se distribuye bajo la **GNU General Public License v3.0**. Consulta
el archivo [LICENSE](LICENSE) para el texto completo.

```
Copyright (C) 2026 BCRP Downloader contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.
```

## Contribuir

Las contribuciones son bienvenidas. Lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de
abrir un *pull request*.
