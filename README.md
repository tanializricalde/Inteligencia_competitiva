# Market Watch

Aplicación interna Django 5.2 para monitorear planes comerciales y reseñas públicas con sus respuestas. Incluye autenticación por correo, permisos, adaptadores HTTPX/Playwright, scheduler separado, outbox de correo, dashboard Tabler y despliegue Docker-first.

Documentación: empieza por el [índice de documentación](docs/README.md). Las referencias principales describen el [stack](docs/TECHNOLOGY_STACK.md), la [arquitectura](docs/ARCHITECTURE.md), la [estructura del repositorio](docs/REPOSITORY_STRUCTURE.md) y el [dashboard configurable](docs/product/DASHBOARD.md).

Antes de contribuir, revisa la propuesta operativa de [AGENTS.md](AGENTS.md): protege datos y
cambios locales, y resume límites arquitectónicos, dependencias y validaciones obligatorias.

## Inicio rápido local

Requisitos: Python 3.12/3.13, Node 20 con Corepack y Chromium compatible con Playwright.

Puedes validar el host con `make dev-check` y automatizar la preparación con `scripts/dev-bootstrap.sh --apply`.

```bash
cp .env.example .env
make setup
make migrate
make assets
.venv/bin/playwright install chromium
make superuser
make dev
```

En otra terminal, inicia la única instancia del scheduler:

```bash
.venv/bin/python manage.py run_scheduler
```

No se ejecutan migraciones automáticamente al arrancar contenedores. Para Docker:

```bash
cp .env.example .env
COMPOSE_PARALLEL_LIMIT=1 docker compose build
docker compose run --rm web python manage.py migrate
docker compose up web scheduler
```

## Comandos

- `make test`: suite pytest secuencial sin navegador.
- `make test-playwright`: Chromium, un proceso, fixtures locales.
- `make lint` / `make format`: Ruff.
- `make assets`: pnpm/Vite con concurrencia baja y assets locales.
- `make migrate`, `make superuser`, `make backup`.
- `make build`: build Compose con `COMPOSE_PARALLEL_LIMIT=1`.
- `make docker-migrate`, `make docker-up`, `make docker-logs` y `make docker-down`: ciclo Docker local.
- `make dev-check`: valida requisitos locales sin modificar el entorno.
- `make deploy-check` / `make nginx-check`: valida Compose, variables y Nginx sin desplegar.
- `make docs-check`: comprueba sintaxis de scripts, Compose y archivos de las guías.
- `make verify`: verificaciones costosas en secuencia.
- `make status`: checkpoint operativo para reanudar trabajo.

## CLI independiente

La extracción también puede ejecutarse sin Django ni base de datos:

```bash
PYTHONPATH=src .venv/bin/python -m scraper_cli validate-config --config config.example.toml
PYTHONPATH=src .venv/bin/python -m scraper_cli all --config config.example.toml --format csv --output-dir output
.venv/bin/python scripts/build_cli_dist.py --output dist/scraper-cli
```

Consulta [arquitectura CLI](docs/cli/CLI_ARCHITECTURE.md), [configuración TOML](docs/cli/CLI_CONFIG.md), [contratos](docs/cli/CLI_OUTPUT_SCHEMAS.md) y [distribución](docs/cli/CLI_DISTRIBUTION.md).

Los archivos extraídos pueden procesarse después, todavía sin Django ni base de datos:

```bash
PYTHONPATH=src .venv/bin/python -m data_cleaning output/reviews.csv --output data/clean/reviews.csv
PYTHONPATH=src .venv/bin/python -m data_transformation data/clean/reviews.csv --output data/normalized/reviews.csv --report data/reports/reviews.json
```

Limpieza elimina y reporta columnas totalmente vacías; transformación conserva los hechos y suma
derivados analíticos. Para características, `--wide-output` publica una vista ancha opcional. Consulta
el [pipeline de datos](docs/data/DATA_PIPELINE.md) para reglas y equivalentes en Windows.

La vista ancha puede consolidar equivalencias por competidor mediante un JSON versionado con
`--feature-rules`; consulta [reglas de equivalencia](docs/data/FEATURE_EQUIVALENCE_RULES.md) para el
schema, ejemplo y reporte.

## Arquitectura

Es un monolito modular. Las reglas de mercado permanecen en `apps.market.domain`; los contratos y parsers de scraping compartidos están en `scraping_core`; los casos de uso en `apps.scraping.application`; ORM, adaptadores y scheduler en infraestructura; views/templates en presentación. Véase [arquitectura](docs/ARCHITECTURE.md) y [agregar proveedores](docs/development/ADDING_A_PROVIDER.md).

`config.example.toml` incluye fixtures offline y una fuente Siigo real deshabilitada; revísala antes de activarla. `python manage.py seed_demo` crea fuentes de ejemplo deshabilitadas que deben reemplazarse explícitamente.
