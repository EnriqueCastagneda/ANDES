# Integración de portales

Regla: la aplicación **nunca** llama a TinyFish en tiempo de ejecución. TinyFish
solo se usa, si hace falta, para descubrir la jerarquía de un portal; el resto se
hace con herramientas locales y el contrato nativo.

## Reparto de herramientas

| Situación | Herramienta | Coste |
| --- | --- | --- |
| API/Swagger/CKAN/SDMX público | `curl` + docs | 0 |
| HTML estático | `curl` + parser | 0 |
| JS público | `scripts/discover_portal.py` (Chromium local) | 0 |
| Login, captcha o flujo interactivo | TinyFish, 1 corrida | 1 |
| Jerarquía imposible de inferir | TinyFish, 1 corrida | 1 |

Presupuesto: máximo 2 corridas de TinyFish por portal, y solo tras fallar el
descubrimiento local.

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
   TinyFish ni servicios intermedios.

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

## INEI — población distrital

- Fuente: `Perú: Población Total Proyectada al 30 de Junio de cada año, según
  Departamento, Provincia y Distrito, 2018–2026` (INEI, XLSX).
- Adaptador `adapters/inei.py`: descarga y cachea el XLSX una vez (30 días),
  lo indexa como una serie por distrito (`INEI-POP-<ubigeo>`) y responde la
  búsqueda desde el catálogo local.
- Frecuencia anual; los periodos son `YYYY-01-01` y `fetch` respeta el rango
  solicitado (años o fechas completas).
- Exportación en los seis formatos (CSV, JSON, XLS, XML, TXT, HTML).
