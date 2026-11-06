# Guía de contribución

Gracias por querer mejorar ANDES.

## Flujo de trabajo

1. Haz un *fork* del repositorio.
2. Crea una rama descriptiva:
   ```bash
   git checkout -b feat/mi-mejora
   ```
3. Instala las dependencias y ejecuta las pruebas:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev,mcp]"
   python -m pytest
   ruff check andes tests scripts app.py
   ```
4. Realiza cambios pequeños y enfocados.
5. Verifica que las pruebas siguen pasando.
6. Haz *commit* siguiendo [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat: añadir exportación a parquet
   fix: corregir filtro por frecuencia
   docs: actualizar README
   ```
7. Abre un *pull request* describiendo el problema y la solución.

## Estilo de código

- Python 3.10+ y formato consistente con el archivo existente.
- Mantén la separación `core` / `gui` / `cli` / `mcp`.
- No añadas dependencias sin justificarlo.
- Para la interfaz usa las APIs de Flet 1.0.x (`ft.Colors`, `ft.Padding`,
  `ft.Icons`, `ft.run`, etc.).

## Pruebas

- Añade pruebas para la lógica nueva cuando sea posible.
- Las pruebas de red deben usar mocks o `skip`.
- Ejecuta la eval web y la responsiva si cambias la interfaz.

## Seguridad y convivencia

- Reporta vulnerabilidades según [`SECURITY.md`](SECURITY.md).
- Sigue el [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- La marca se rige por [`TRADEMARKS.md`](TRADEMARKS.md).

## Licencia de las contribuciones

Al enviar un *pull request* aceptas que tu contribución se publique bajo la
**GNU General Public License v3.0**, la misma licencia del proyecto.
