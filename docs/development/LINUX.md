# Desarrollo en Linux desde cero

Ejecuta todos los comandos desde la raíz del repositorio. Esta ruta usa Bash, Python 3.12/3.13,
Node.js 20 con Corepack y SQLite local. Docker es opcional.

## 1. Preparar el host

Instala Python con soporte para `venv`, Node.js 20, Corepack y las librerías que Playwright requiera
en tu distribución. Comprueba sin modificar el proyecto:

```bash
scripts/dev-bootstrap.sh --check
python3 --version
node --version
corepack pnpm --version
```

## 2. Crear el entorno

El camino automatizado no sobrescribe un `.env` existente:

```bash
scripts/dev-bootstrap.sh --apply
```

Ese comando crea `.env` desde `.env.example` cuando falta, crea `.venv`, instala
`requirements.lock`, instala el proyecto, compila el frontend, instala Chromium, crea `data/`,
aplica migraciones y ejecuta `manage.py check`.
También siembra de forma idempotente los proveedores, fuentes y perfil del pipeline.

El equivalente manual es:

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -e . --no-deps
corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
NODE_OPTIONS=--max-old-space-size=1536 corepack pnpm --dir frontend build
.venv/bin/python -m playwright install chromium
mkdir -p data
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_market_pipeline
.venv/bin/python manage.py check
```

Cambia `SECRET_KEY` en `.env`. Para acceso sólo local conserva `DEBUG=true`, hosts localhost y
cookies no seguras como en `.env.example`. No reutilices esa configuración en producción. Consulta
[Variables de entorno](ENVIRONMENT_VARIABLES.md) para tipos, ejemplos y rutas.

## 3. Crear datos iniciales y usuario

El bootstrap anterior ya ejecutó `seed_market_pipeline`; puedes repetirlo sin duplicar registros.

```bash
.venv/bin/python manage.py createsuperuser
```

El superusuario usa correo y contraseña. `seed_demo` es opcional y no crea usuarios:

```bash
.venv/bin/python manage.py seed_demo
```

## 4. Levantar Django y scheduler

Terminal 1:

```bash
make dev
```

Terminal 2:

```bash
make scheduler
```

Comprueba:

```bash
curl -fsS http://127.0.0.1:8000/public/health
curl -fsS http://127.0.0.1:8000/public/ready
```

Abre `http://127.0.0.1:8000/accounts/login/` o `/admin/`. Para detener el entorno pulsa `Ctrl+C`
en ambas terminales. Esto no borra `data/market-watch.sqlite3`.

## 5. Cambios en `frontend/`

Después de cualquier modificación en `frontend/src/`:

```bash
make assets
git status --short src/static/dist
```

`make assets` instala exactamente el lock de pnpm y ejecuta el build Vite. La salida es
`src/static/dist/`; nunca la edites directamente. `runserver` suele detectar los archivos nuevos;
recarga el navegador y, si no aparecen, reinicia sólo el proceso web. El scheduler no necesita
reinicio por un cambio exclusivamente visual.

Si validas con Docker, la imagen contiene los assets y debes reconstruir y recrear los servicios:

```bash
make build
make docker-up
```

En producción sigue el procedimiento de actualización de
[Producción con Nginx](../operations/DEPLOYMENT_NGINX.md#actualizar-código-y-assets).

## 6. Alternativa Docker

```bash
cp .env.example .env
docker compose build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose up -d web scheduler
docker compose ps
```

Detén sin eliminar volúmenes:

```bash
docker compose down
```

No uses `docker compose down -v` si deseas conservar usuarios y datos. La base Docker vive en un
volumen y no es la misma que `data/market-watch.sqlite3` del entorno nativo.

## 7. Validación habitual

```bash
make lint
make test
make docs-check
```

Usa `make test-playwright` sólo cuando el cambio requiere Chromium. Para más contexto consulta la
[guía común](DEVELOPMENT.md) y [uso de recursos](../operations/RESOURCE_USAGE.md).
