# BCRP Downloader

Aplicación de escritorio en Python (Flet 1.0.5, pandas y requests) para explorar el catálogo de series estadísticas del Banco Central de Reserva del Perú (BCRP) y descargar sus series temporales.

## Características

- Interfaz oscura tipo Bento con dos paneles que crecen con la ventana.
- Búsqueda global por código o nombre, selector de frecuencia (Todos, Diaria, Mensual, Trimestral, Anual) y filtros avanzados (área, fuente, categoría, grupo, rangos de fecha de creación y actualización).
- Selección múltiple, navegación por teclado (↑/↓ para mover, Enter/Espacio para seleccionar) y descarga simple o en lote.
- Formatos: CSV, JSON, XLS, XML, TXT y HTML.
- Inspector de metadatos con botón a la documentación PDF cuando la descripción incluye un enlace `.pdf`.
- Reintentos HTTP y detección de la página de bloqueo de la CDN.

## Requisitos

- Python >= 3.10
- Flet 1.0.5, pandas >= 2.2, requests >= 2.31

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate   # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecución

```bash
python app.py
```

Para ejecutarla en el navegador como alternativa: `flet run --web app.py`.

## Uso

1. Escribe en el buscador o elige una frecuencia; abre "Filtros Avanzados" para refinar.
2. Haz clic en una tarjeta para seleccionarla y ver sus metadatos.
3. Define fechas y formato en el panel derecho y pulsa "Descargar".
4. Los archivos se guardan en `outputs/`; el catálogo se guarda en `data/metadata_bcrp.csv` (solo se descarga si no existe).

## Estructura

```
app.py                  # toda la aplicación
requirements.txt
pyproject.toml
tests/                  # pruebas pytest
.github/workflows/      # ci.yml y build.yml
```

## Pruebas

```bash
python -m pytest -q
```

Las pruebas que dependen de la red se omiten si la API del BCRP no responde.

## Integración continua

`ci.yml` se ejecuta en push a main/master, pull requests y manualmente, con Python 3.10 y 3.12: compila `app.py` y ejecuta pytest.

## Matriz de build

`build.yml` usa `flet-dev/flet-build-action@v1` y genera artefactos para:

| Plataforma | Runner |
|---|---|
| Linux | ubuntu-latest |
| Windows | windows-latest |
| macOS | macos-latest |
| Android (APK) | ubuntu-latest |
| Web | ubuntu-latest |

iOS no se compila. Los artefactos se llaman `bcrp-downloader-<target>-<version>.zip` (Linux: `.tar.gz`).

## Publicar una versión

- **Por tag:** `git tag v1.0.0 && git push origin v1.0.0` compila y publica el release automáticamente.
- **Manual:** ejecuta el workflow *Build* con `workflow_dispatch`, marcando `publish_release` e indicando `release_tag`.

| Pregunta | Respuesta |
|---|---|
| Entrypoint | `app.py` (estructura propia, resuelto con `tool.flet.app.module`) |
| Gestor de dependencias | `pip + requirements.txt` en desarrollo; `pyproject.toml` para el build |
| Plataformas | Linux, Windows, macOS, Android y Web (sin iOS) |
| Publicación | Automática por tag `v*` y manual por `workflow_dispatch` |

## Datos y API

- Metadatos (CSV, `;`, latin-1): `https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata`
- Series: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigo}/{formato}/{inicio}/{fin}/esp`

El BCRP devuelve JSON válido con `Content-Type: text/html` y su CDN responde ocasionalmente con una página HTML de bloqueo; la aplicación lo maneja con reintentos.

## Licencia

GNU GPL v3 o posterior. Ver [LICENSE](LICENSE).
