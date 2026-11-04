# Publicar en PyPI

El proyecto usa **Trusted Publishing (OIDC)**: no se guardan tokens en GitHub.
GitHub emite un token efímero que PyPI valida contra el repositorio y el workflow.

## Paso único en PyPI

1. Inicia sesión en <https://pypi.org>.
2. Ve a **Account settings → Publishing → Add a pending publisher**.
3. Rellena:

| Campo | Valor |
| --- | --- |
| PyPI project name | `bcrp-downloader` |
| Owner | `EnriqueCastagneda` |
| Repository name | `BCRP-Downloader` |
| Workflow name | `build_release.yml` |
| Environment name | `pypi` |

4. Guarda. El proyecto se creará con la primera publicación.

## Publicar

```bash
git tag -a v1.1.1 -m "BCRP Downloader v1.1.1"
git push origin v1.1.1
```

El job `Publish to PyPI` de `build_release.yml` construye `sdist`/`wheel`,
los valida con `twine check` y los sube usando el token OIDC.

Para una ejecución manual sin tag: *Actions → Build and release → Run workflow*
y activa `publish_pypi`.

## Alternativa con token (no recomendada)

Si prefieres un token clásico, crea uno en
<https://pypi.org/manage/account/token/> y añade el secreto
`PYPI_API_TOKEN` en *Settings → Secrets and variables → Actions*. Luego
restaura `password: ${{ secrets.PYPI_API_TOKEN }}` en el paso de publicación.
