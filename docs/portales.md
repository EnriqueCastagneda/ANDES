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

## Añadir una dimensión a la GUI

La sección MEF se construye desde `portals.spec_for("mef").dimensions`. Para un
portal nuevo, declarar sus dimensiones en `portals.py` basta para que la GUI
genere sus desplegables; solo los casos especiales (frecuencia, rangos de fecha)
requieren controles propios.

## Estado actual

- **BCRP**: catálogo SQLite+FTS5, lotes de 10, adaptador nativo.
- **MEF**: jerarquía declarada (Año 1999–2026, Nivel de gobierno, Rubro, Fuente,
  Programa) y descubrimiento local en `fixtures/mef/discovered.json`
  (`DrpYear`, `DrpActProy`, `Navegar_7.aspx`). Falta el endpoint de datos; el
  adaptador devuelve vacío y `fetch` falla de forma explícita.
