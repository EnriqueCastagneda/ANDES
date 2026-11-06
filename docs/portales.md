# Integración de portales

Regla: la integración se hace **solo con herramientas locales** del repositorio.
No se usan agentes ni servicios externos, ni en tiempo de ejecución ni durante el
descubrimiento.

## Reparto de herramientas

| Situación | Herramienta | Coste |
| --- | --- | --- |
| API/Swagger/CKAN/SDMX público | `curl` + docs | 0 |
| HTML estático | `curl` + parser | 0 |
| JS público | `scripts/discover_portal.py` (Chromium local) | 0 |
| Login, captcha o flujo interactivo | no automatizado: se documenta como pendiente | 0 |
| Jerarquía difícil de inferir | inspección manual con Chromium local | 0 |

## Flujo

1. **Descubrir** con Chromium local:

   ```bash
   python scripts/discover_portal.py https://portal.gob.pe/ruta \
       --out fixtures/<portal>/discovered.json
   ```

   Captura peticiones XHR/fetch y los `<select>` de todas las frames. No usa
   servicios externos.

2. **Curar** el borrador en `fixtures/<portal>/hierarchy.json` con este contrato:

   ```json
   {
     "id": "portal",
     "name": "Nombre completo",
     "short_name": "SIGLA",
     "base_url": "https://...",
     "endpoints": {"series": "https://.../{param}"},
     "period_format": "2026",
     "pagination": "",
     "dimensions": [
       {"key": "inicio", "label": "Año", "kind": "select", "options": ["2026"]}
     ],
     "pending": ["series"]
   }
   ```

   `key` es la clave que entiende `catalog.search` (`inicio`, `categoria`,
   `fuente`, `grupo_serie`, `grupo_publicacion`, …).

3. **Declarar** la institución en `core/sources.py` (id, nombre, URLs y
   `filter_options` iniciales) y sus dimensiones/endpoints en
   `core/portals.py`.

4. **Implementar el adaptador** en `core/adapters/<portal>.py`:

   ```python
   class PortalAdapter:
       spec = spec_for("portal")
       def search(self, query, *, filters=None, limit=100, offset=0): ...
       def fetch(self, codes, start, end, frequency=None): ...
   ```

   `search` usa el catálogo local; `fetch` habla directo con el portal. Sin
   servicios intermedios.

5. **Registrar** el adaptador en `core/adapters/__init__.py`.

6. **Versionar y probar**:

   ```bash
   python scripts/export_specs.py   # fixtures desde el contrato
   pytest -q
   python scripts/eval_web_gui.py   # GUI en marcha
   ```

## Filtros en la GUI

El selector de institución y el botón de filtros viven en la misma fila. Los
filtros de cada institución están plegados por defecto y todos sus valores
arrancan en «Todos»; el botón los muestra u oculta sin ocupar espacio permanente
en la lista.

## Añadir una dimensión a la GUI

La sección MEF se construye desde `portals.spec_for("mef").dimensions`. Para un
portal nuevo, declarar sus dimensiones en `portals.py` basta para que la GUI
genere sus desplegables; solo los casos especiales (frecuencia, rangos de fecha)
requieren controles propios.

## Estado actual

- **BCRP**: catálogo SQLite+FTS5, lotes de 10, adaptador nativo.
- **MEF**: dos colecciones nativas. Transferencias (mensual, 2010–2026, API
  `datastore_search`/`dump`) y Cuadros estadísticos (61 archivos `.xls` de la
  página de Estadísticas, normalizados a ~1 030 series anuales/trimestrales con
  caché local). Jerarquía declarada: Año 1999–2026, Nivel de gobierno, Rubro,
  Fuente y Programa.
  La primera búsqueda de un término indexa en el catálogo local los conceptos
  encontrados (p. ej. «canon» → Canon Minero, Canon Forestal, Canon Pesquero…) y
  las siguientes son instantáneas. `fetch` agrega los montos mensuales del
  recurso más reciente de Transferencias y respeta el rango pedido (`2026-02` a
  `2026-04`) y recorre todos los años disponibles (2010–2026) usando el CSV
  filtrado de cada recurso, con caché local por año. Las series guardan
  inicio/fin mensuales reales (p. ej. `2026-01` a `2026-10`).

## INEI Población Proyectada — población distrital

- Fuente: `Perú: Población Total Proyectada al 30 de Junio de cada año, según
  Departamento, Provincia y Distrito, 2018–2026` (INEI, XLSX).
- Adaptador `adapters/inei.py`: descarga y cachea el XLSX una vez (30 días),
  lo indexa como una serie por distrito (`INEI-POP-<ubigeo>`) y responde la
  búsqueda desde el catálogo local.
- Frecuencia anual; los periodos son `YYYY-01-01` y `fetch` respeta el rango
  solicitado (años o fechas completas).
- Archivo único: la GUI bloquea las fechas y fija la salida en XLS.

## INEI Temático — índice temático

- Fuente: `https://www.inei.gob.pe/estadisticas-indice-tematico/`.
- El adaptador descubre en vivo las categorías del índice (Economía, Población
  y Vivienda, Empleo, Sociales, Medio Ambiente, TIC, Seguridad Ciudadana e
  Indicadores de Género) y los archivos `.xls/.xlsx/.xlsm/.csv` enlazados en
  cada una. No hay lista fija: si el INEI agrega o quita archivos, el índice se
  reconstruye (caché de 7 días) y el catálogo se reemplaza.
- Cada archivo es un registro `INEI-TEM-<hash>` con categoría y sección; la
  búsqueda es local. Al descargar se lee la tabla (detección de encabezado) y se
  exporta a CSV.
- Archivo único: la GUI bloquea las fechas y fija la salida en CSV.

## Portales institucionales — servicios estadísticos de Gob.pe

- Fuente: buscador de Gob.pe, `https://www.gob.pe/busquedas?term=estadisticas`.
  El endpoint JSON (`/busquedas.json?term=...&sheet=N`) expone 25 resultados por
  página; el término «estadisticas» devuelve ~46 335 resultados en 1 854
  páginas.
- `scripts/discover_gobpe.py` recorre todas las páginas (reanudable), deduplica
  por URL y clasifica cada destino: `csv`, `excel`, `api`, `ckan`, `tableau`,
  `powerbi`, `pdf`, `web`, `gobpe`.
- El registro se guarda en `data/gobpe/portals.json` (semilla versionada en
  `fixtures/gobpe/portals.json`). Cada portal se atribuye a su institución real
  (`content_sub_title_card`), con id `gobpe:<institución>`; el selector muestra
  el nombre de la institución, nunca un agrupador «Gob.pe».
- Prefijos repetidos se agrupan para no inflar el menú: `MUNI*` →
  **Municipalidades**, `REGION*` → **Regiones**, `UGEL*` → **UGEL**,
  `RED*` → **Redes de Salud**. Las reglas están en `gobpe.GROUP_RULES`.
- Cada opción del selector lleva un globo (tooltip) con el nombre completo de
  la institución cuando la etiqueta es una sigla.
- El adaptador indexa cada portal como `GOBPE-<hash>` con plataforma (filtro).
- Descarga: solo plataformas tabulares (CSV, Excel, API/JSON). Tableau, Power BI,
  PDF y páginas web se abren como enlace externo.
- Archivo único: fechas bloqueadas y salida fija en CSV.
