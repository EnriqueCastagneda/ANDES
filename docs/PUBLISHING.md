# Publicar en PyPI

El proyecto publica con un **token de PyPI** guardado como secreto
`PYPI_API_TOKEN` (necesario porque el proyecto se creó con token; Trusted
Publishing queda como alternativa). El workflow `publish_pypi.yml` permite
publicar manualmente y `build_release.yml` publica al crear un tag `v*`.

## Configuración con token

1. Crea un token en <https://pypi.org/manage/account/token/> (scope *Entire account*
   la primera vez; luego puedes restringirlo al proyecto).
2. Añádelo en GitHub → Settings → Secrets and variables → Actions como
   `PYPI_API_TOKEN`.
3. Ejecuta el workflow **Publish to PyPI** o crea un tag `v*`.

## Publicar

```bash
git tag -a v1.1.2 -m "BCRP Downloader v1.1.2"
git push origin v1.1.2
```

El job `Publish to PyPI` construye `sdist`/`wheel`, los valida con `twine check`
y los sube usando el token (`skip-existing` evita fallos por reintentos).

Para una ejecución manual sin tag: *Actions → Build and release → Run workflow*
y activa `publish_pypi`.

## Alternativa con token (no recomendada)

Si prefieres un token clásico, crea uno en
<https://pypi.org/manage/account/token/> y añade el secreto
`PYPI_API_TOKEN` en *Settings → Secrets and variables → Actions*. Luego
restaura `password: ${{ secrets.PYPI_API_TOKEN }}` en el paso de publicación.
