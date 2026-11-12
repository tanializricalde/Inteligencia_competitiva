# Uso conservador de recursos

Todos los targets son secuenciales (`.NOTPARALLEL`). Valores predeterminados: `TEST_WORKERS=1`, `PLAYWRIGHT_WORKERS=1`, `COMPOSE_PARALLEL_LIMIT=1`, `NODE_MAX_OLD_SPACE_SIZE=1536`.

- Empieza con prueba sintáctica y un archivo pytest; ejecuta `make test` después.
- `make test` no instala xdist ni crea workers. `make test-playwright` usa solo Chromium y fixtures locales.
- `make assets` usa `child-concurrency=1`, cuatro descargas y límite de memoria Node.
- `make build` limita Compose a un build simultáneo. No uses `--no-cache` salvo diagnóstico.
- No ejecutes instalación, suite, navegador y Docker a la vez. No uses `make -j` sin número.

Antes de una operación costosa actualiza `docs/PROGRESS.md`. Si se interrumpe, ejecuta `make status`, lee la siguiente acción y repite solo el último grupo no confirmado. Conserva cachés de pip, pnpm, Playwright y Docker. Si hay presión de recursos, reduce el grupo; no repitas sin cambios.

