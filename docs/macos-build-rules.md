# Reglas de build y verificación de macOS

Referencia para el job `macos` de `.github/workflows/build_release.yml`
(Flet 1.0.5, Python 3.12 empaquetado).

## Estructura esperada del bundle

`flet build macos` produce `andes.app` con:

- `Contents/MacOS/andes` — ejecutable que lanza la app.
- `Contents/Resources/` — assets, iconos y manifiesto.
- `Contents/Info.plist` — identificador, nombre y versión del bundle.

El workflow verifica el `.app` después de compilar. Si falta el directorio o el
ejecutable, el job falla y el release no se publica.

## Verificación en CI

```yaml
- name: Verify macOS app bundle structure
  if: matrix.target == 'macos'
  shell: bash
  run: |
    set -euo pipefail
    UNZIP_DIR=$(mktemp -d)
    unzip -q "${{ steps.build.outputs.archive-path }}" -d "$UNZIP_DIR"
    APP_DIR=$(find "$UNZIP_DIR" -maxdepth 1 -type d -name "*.app" -print -quit)
    test -n "$APP_DIR"
    test -f "$APP_DIR/Contents/MacOS/andes"
```

Además, `test_and_lint.yml` ejecuta la suite completa en `macos-latest` con
Python 3.10 y 3.12.

## Rutas de datos

En una app congelada (`sys.frozen`), los datos y la configuración se guardan en
`~/Library/Application Support/andes`. En desarrollo se usa `data/`.
La lógica vive en `andes/core/paths.py` y se prueba en `tests/test_paths.py` y
`tests/test_preferences.py`.

macOS (HFS+/APFS) almacena los nombres con acentos en NFD. `normalize_output_path`
y `load_output_dir` normalizan a NFC antes de comparar o persistir.

## Gatekeeper

El `.app` no está firmado ni notarizado. Al descargarlo de Internet, macOS puede
bloquearlo. El README documenta la solución:

```bash
xattr -d com.apple.quarantine /Applications/ANDES.app
```

También se puede abrir con Ctrl+clic → «Abrir».

## Errores frecuentes

| Síntoma | Causa | Corrección |
| --- | --- | --- |
| La app no abre | Falta `Contents/MacOS/andes` | Revisar la verificación del bundle |
| Gatekeeper lo bloquea | Cuarentena de descarga | `xattr -d com.apple.quarantine` |
| No encuentra los datos | Ruta de usuario distinta | Revisar `~/Library/Application Support/andes` |
| Falla solo en Apple Silicon | Binario de otra arquitectura | Compilar en el mismo tipo de runner |
