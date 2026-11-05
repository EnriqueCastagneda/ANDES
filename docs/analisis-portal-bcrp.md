# BCRPData: análisis del portal e integración acelerada

Fecha: 2026-11-05 · App analizada: [BCRP-Downloader](https://github.com/EnriqueCastagneda/BCRP-Downloader) (Python 3.10+, Flet 1.0.5, pandas, requests, Typer, MCP)

## 1. Resumen

El portal `estadisticas.bcrp.gob.pe` **ya expone una API pública** documentada. No hace
falta navegar menús, resolver JavaScript ni descargar planillas: la app puede leer
catálogo y datos por HTTP directo. El problema real no es el aspecto visual, es que el
portal está detrás de **Imperva (Incapsula)** y devuelve **HTTP 200 con una página HTML**
cuando detecta ráfagas. El cliente actual reintenta de inmediato, sin espaciar, y cae en
ese muro.

Medición con el cliente actual frente al nuevo, mismas 20 series mensuales
(`2024-1` a `2024-12`):

| Cliente | Peticiones | Tiempo | Notas |
| --- | ---: | ---: | --- |
| Actual (1 serie por petición, `requests`) | 20 | 4,8–28,9 s | el extremo alto incluye bloqueos y reintentos |
| Nuevo (lotes de 10, sesión única, rate-limit) | 2 | 0,69 s | 0 bloqueos |
| Nuevo con caché caliente | 0 | ~0,00 s | 2 aciertos de caché |

**Aceleración: 6,9x en frío y hasta 41x cuando el cliente anterior cae en la
página de Imperva.** Catálogo: el CSV de 6,9 MB tarda ~9 s en descargarse y más en
cargarse con pandas; el índice SQLite+FTS5 responde búsquedas en **0,4–4 ms** y el
arranque posterior es instantáneo.

## 2. Mapa real del portal (lo que sí sirve)

| Recurso | URL | Uso |
| --- | --- | --- |
| API de series | `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigos}/{formato}/{inicio}/{fin}/{idioma}` | Datos |
| Catálogo completo | `https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata` | CSV 6,9 MB, 17 167 series |
| Buscador | `POST /estadisticas/series/buscador` (`txtbuscador`, `accion=buscar`) | Alternativa HTML, ~0,59 s |
| Metadatos (página) | `/estadisticas/series/ayuda/metadatos` | Solo enlaza al CSV |
| Condiciones de uso | `/estadisticas/series/ayuda/condiciones-de-uso` | Marco legal |
| Guía API (PDF) | `/estadisticas/series/documentos/bcrpdataapi.pdf` | Sintaxis de periodos |

Formatos del API: `html` (por defecto), `grafico` (Flash, obsoleto), `xls`, `xml`,
`json`, `jsonp`, `txt`, `csv`. Método GET y POST. Idioma `esp`/`ing`.

Respuesta JSON:

```json
{"config":{"title":"...","series":[{"name":"...","dec":"3"}]},
 "periods":[{"name":"03.Nov.25","values":["3.37492857142857"]}]}
```

`values` es un arreglo alineado al orden de `config.series`: un solo payload sirve para
hasta 10 series.

## 3. Rarezas y trampas (verificadas)

1. **JSON servido como `text/html`**. Nunca decidas por `Content-Type`; decide por el
   cuerpo (`{`/`[`) y por `json.loads`.
2. **Bloqueo con HTTP 200**. Imperva responde `text/html` con
   `/_Incapsula_Resource?...`. Con 12 peticiones simultáneas: **11 de 12 bloqueadas**.
   Secuencial con cookies y 0,5 s: **9 de 10**. El bloqueo es probabilístico, no un
   `429`.
3. **Sin caché HTTP**. `cache-control: no-cache`, sin `ETag`, sin `Last-Modified`, sin
   `Content-Encoding`, sin `Accept-Ranges` (verificado con `Range: bytes=0-99` → 200
   completo). La caché debe ser local.
4. **Máximo real: 10 series por petición**. Con 11 el API respondió igual (las devuelve),
   pero la documentación fija 10; no lo uses como contrato.
5. **Frecuencias mezcladas se descartan en silencio**. `PN02436FQ` (trimestral) +
   `PN00001MM` (mensual) devuelve **solo** la primera. Hay que agrupar por frecuencia.
6. **Sintaxis de periodo por frecuencia**: diaria `2026-11-5`, mensual `2026-11`,
   trimestral `2026-4` (no `2026-T4`), anual `2026`. Un periodo inválido devuelve la
   página de Imperva, no un error legible.
7. **Valores faltantes**: `"n.d."` (también llegan cadenas vacías). Convertir a `None`;
   no usar `float()` directo.
8. **Etiquetas de fecha no ISO**: `01.Ene.97`, `Ene.2024`, `T1.20`, `2025`. Requieren
   normalización; el año de dos dígitos necesita pivote (`97` → 1997, `26` → 2026).
9. **Catálogo en ISO-8859-1 con `;`** y 19 columnas; incluye categoría, grupo, unidad,
   fuente, frecuencia y vigencia. Contiene tildes: usar `latin-1`/`cp1252` y FTS5 con
   `remove_diacritics 2`.
10. **Sin CORS**. No hay `Access-Control-Allow-Origin`; una build Flet *web* no puede
    llamar al API desde el navegador. La descarga debe ejecutarse en el proceso Python.
11. **Rango histórico**. Una serie diaria completa son 7 827 puntos, ~40 KB y 1,65 s;
    pedir solo el tramo necesario reduce tiempo y exposición.
12. **Portal de datos abiertos** (`datosabiertos.gob.pe`) devolvió **HTTP 418** a este
    cliente: no es una vía fiable. El CSV de metadatos es la única fuente masiva estable.

## 4. Marco legal y de uso aceptable

Condiciones de uso del BCRP (texto vigente):

> «Puede reproducirse total o parcialmente, sin autorización expresa, siempre y cuando
> se cite la fuente.»

Consecuencias prácticas:

- **Sí**: consumir la API pública, cachear, redistribuir datos **citando “Fuente:
  BCRPData”** y la fecha de corte.
- **Sí**: automatizar con rate-limit conservador y User-Agent identificable.
- **No**: resolver o evadir el desafío de Imperva, rotar proxies para saltar el WAF,
  paralelizar agresivamente ni raspar el buscador para reconstruir el catálogo cuando el
  CSV oficial ya lo entrega.
- **No** asumir estabilidad: el BCRP puede cambiar el portal sin aviso. Versiona el
  parser y degrada con elegancia.

La estrategia de este diseño **no evade** el WAF: reduce peticiones (lotes), reutiliza
sesión y cookies legítimas, espacia y reintenta con backoff. Eso es uso cortés, no
bypass.

## 5. Diseño de integración (encaja en la arquitectura actual)

Dos módulos nuevos en `bcrp_downloader/core/`, sin dependencias nuevas:

### `catalog.py` — catálogo local SQLite + FTS5

- Descarga el CSV **una vez al día** (TTL 24 h) y reconstruye de forma atómica
  (`*.part` + `os.replace`).
- Tabla `series` con las 18 columnas útiles; tabla virtual `series_fts` con
  `code, name, group_name, category, unit`, `tokenize="unicode61 remove_diacritics 2"`.
- `search(query, frequency=..., category=..., limit=..., offset=...)` usa prefijos
  (`"tipo"* "camb"*`) y `bm25()`; búsqueda vacía = listado filtrado.
- Si la descarga falla, sigue usando el catálogo anterior (modo offline).

### `fetcher.py` — descarga por lotes

- Agrupa por frecuencia y parte en lotes de 10.
- Sesión `requests.Session` única (keep-alive + cookies `PHPSESSID`/`incap_ses`) y
  headers de navegador.
- `_Gate`: 2 hilos como máximo y 0,45 s entre arranques de petición.
- Reintentos: 5 intentos, backoff `min(8, 0.4·2^n)` + jitter y penalización extra de 2 s
  por intento cuando el bloqueo es de Imperva.
- Caché SQLite por lote: histórico (año anterior) 30 días; año en curso 1 hora.
- Normaliza fechas a ISO, `n.d.` → `None`, y devuelve `{codigo: [{fecha, periodo, valor}]}`.
- Si un lote devuelve menos series de las pedidas (código inválido o baja silenciosa),
  reintenta esos códigos uno a uno.

### Puntos de conexión en el repo

| Archivo actual | Cambio |
| --- | --- |
| `core/metadata.py` | `load_metadata()` deja de cargar 6,9 MB con pandas en cada arranque; `search`/`filter_metadata` pasan a `catalog.search(...)`. Mantener `load_metadata()` como compatibilidad (descarga perezosa). |
| `core/api.py` | `download_series_data()` delega en `fetcher.fetch_series([code], ...)`; añadir `download_many(codes, ...)` para lotes. |
| `core/http.py` | Reutilizar `_is_block`; el nuevo cliente ya incorpora detección y backoff (no borrar el módulo: lo usan tests y descargas XLS). |
| `gui/views.py` | Implementado: búsqueda y filtros vía `search_catalog()`, descarga por lotes con `download_many()` agrupada por frecuencia, progreso por lote y respaldo serie por serie. |
| `cli/main.py` | Nuevo `bcrp download-many --codes ... --frequency Mensual` y `bcrp catalog refresh`. |
| `mcp/server.py` | `search_series` usa FTS5; `download_series` acepta lista de códigos. |

### Flujo recomendado

```
arranque → ¿catálogo fresco? ──no──> descarga CSV (background) → indexa SQLite
                │sí
                └──> búsqueda local (ms)

usuario elige N series
   → agrupar por frecuencia
   → lotes de 10
   → gate (2 hilos, 0,45 s) → sesión única → reintento con backoff
   → caché SQLite → DataFrame/CSV/XLS/JSON
```

## 6. Recetas de velocidad para Flet

1. **Nunca bloquear el hilo de UI**: `page.run_thread(...)` o `asyncio.to_thread`; el
   catálogo ya es local, pero la descarga no.
2. **Búsqueda local con debounce** (250–300 ms) y `limit=50`; paginar con
   `offset` en vez de renderizar 17 000 filas.
3. **`ft.ListView` con `item_extent` fijo** o carga incremental; evita `Column` con
   miles de controles.
4. **Una sola `page.update()` por lote** de cambios; no actualizar por fila.
5. **Progreso real por lotes**: `progreso = lotes_ok / total_lotes`.
6. **Caché en disco** en `BCRP_DATA_DIR` (respetar la variable ya existente) para que
   funcione en escritorio, Android y web self-hosted.
7. **Modo offline**: si el portal bloquea, mostrar catálogo y datos cacheados con aviso
   de “datos al <fecha>”; no fallar la pantalla.
8. **Copiar al portapapeles / exportar por streaming** (`yield` por fila) para series
   diarias largas.

## 7. Pruebas de aceptación

- `catalog.search("inflacion")` devuelve resultados en < 20 ms con tildes y prefijos.
- `fetcher.fetch_series(20 códigos mensuales, "2024-1", "2024-12")` ≤ 2 peticiones y
  < 2 s en frío.
- Mismos valores que el cliente anterior para `PD04638PD` en un rango de 10 días
  (verificado: coinciden).
- Ante un bloqueo HTML, el cliente reintenta y termina; no lanza `JSONDecodeError`.
- Segunda ejecución idéntica: 0 peticiones (caché).
- Serie inexistente: error claro, sin bucle de reintentos infinito.

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
| --- | --- |
| Imperva endurece el bloqueo | bajar a 1 hilo y 1 s; circuit breaker y aviso al usuario |
| Cambio de sintaxis/columnas | parser tolerante + tests con fixture del CSV |
| CSV crece | indexación incremental por `Fecha de actualización` (siguiente iteración) |
| Uso comercial de los datos | citar BCRPData; revisar condiciones antes de redistribuir |
| Build web sin acceso directo | mantener todo el HTTP en el backend Python |

## 9. Entregables

```
bcrp-integracion/
├── bcrp_downloader/core/catalog.py     # catálogo SQLite + FTS5
├── bcrp_downloader/core/fetcher.py     # lotes, rate-limit, backoff, caché
├── scripts/bench_portal.py             # benchmark reproducible
├── tests/test_fast_portal.py           # pruebas sin red
└── BCRP-portal-analisis.md             # este documento
```

Integrado en la rama `feat/portal-rapido` del repo principal:

- `core/catalog.py`, `core/fetcher.py`, `core/sources.py` (registro de
  instituciones de origen), `scripts/bench_portal.py`, `tests/test_fast_portal.py`.
- Filtro `institucion` en `catalog.search()` y en la GUI; al añadir una fuente se
  declara en `sources.py` y aparece en el desplegable «Institución».
- `core/metadata.py`: `search_catalog()`, `series_info()`, `frequency_for()`,
  `catalog_frequencies()` (mismas columnas que `load_metadata`).
- `core/api.py`: `download_many(codes, start, end, frequency=None)`.
- `cli/main.py`: comando `bcrp download-many`.
- `tests/test_fast_integration.py`: adaptadores y CLI.
- `tests/test_gui_catalog.py`: prueba de humo de la GUI con `Page` falso.

No requiere cambios en `pyproject.toml`.
