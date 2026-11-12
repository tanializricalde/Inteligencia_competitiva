# Guía de desarrollo

Esta guía describe el entorno local, el ciclo diario y las verificaciones del proyecto. Los comandos conservan un solo worker/proceso salvo que el desarrollador decida explícitamente otra cosa. Los bloques Bash son para Linux. En Windows usa PowerShell y los equivalentes completos de [Linux y Windows](WINDOWS_LINUX.md), en particular `.\.venv\Scripts\python.exe` en lugar de `.venv/bin/python`.

## 1. Requisitos

- Linux o Windows con Python 3.12 o 3.13. El despliegue Nginx/systemd sí requiere Linux.
- Node.js 20 y Corepack. El repositorio fija pnpm en `frontend/package.json`.
- SQLite 3.
- Docker Engine con Compose v2, solo si se usa el flujo en contenedores.
- Chromium de Playwright para las pruebas marcadas `playwright`.
- PowerShell 5.1 o 7 en Windows; Bash en Linux. El validador de enlaces usa sólo Python.

Para un recorrido realmente desde cero usa [Linux](LINUX.md) o [Windows](WINDOWS.md). En Linux,
comprueba el host sin modificarlo:

```bash
scripts/dev-bootstrap.sh --check
```

## 2. Instalación nativa

El bootstrap no sobrescribe un `.env` existente. Si no existe, copia `.env.example`, instala dependencias bloqueadas, compila assets, instala únicamente Chromium, aplica migraciones y ejecuta el check de Django.

```bash
scripts/dev-bootstrap.sh --apply
```

`dev-bootstrap.sh` y `make` requieren Bash/Linux. En Windows usa el equivalente automatizado:

```powershell
.\scripts\dev-bootstrap.ps1 -Apply
```

Si necesitas evaluar la imagen y settings productivos sin dominio/certificado, no cambies este
flujo nativo: usa el perfil acotado de
[producción local por HTTP](../operations/PRODUCTION.md#evaluar-la-producción-localmente-sin-dominio-ni-https).

O realiza el proceso manual:

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
corepack pnpm --dir frontend build
.\.venv\Scripts\python.exe -m playwright install chromium
New-Item -ItemType Directory -Force data
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_market_pipeline
.\.venv\Scripts\python.exe manage.py check
```

Equivalente manual:

```bash
cp .env.example .env
make setup
make assets
.venv/bin/playwright install chromium
make migrate
.venv/bin/python manage.py check
```

`make migrate`, `Makefile.ps1 migrate` y los bootstrap cargan también los catálogos y perfil
idempotentes del pipeline. Si ejecutaste `manage.py migrate` directamente, completa el paso con:

```bash
.venv/bin/python manage.py seed_market_pipeline
```

En Windows: `.\.venv\Scripts\python.exe manage.py seed_market_pipeline`. La guía de comandos,
importación y regeneración segura está en [Pipeline Django](../data/DJANGO_PIPELINE.md).

Antes de crear usuarios, cambia al menos `SECRET_KEY` en `.env`. La
[referencia de variables](ENVIRONMENT_VARIABLES.md) explica tipos, precedencia, defaults y rutas
Linux/Windows/Docker. Para desarrollo local conserva:

```dotenv
DEBUG=true
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000
APP_BASE_URL=http://localhost:8000
SECURE_SSL_REDIRECT=false
SESSION_COOKIE_SECURE=false
CSRF_COOKIE_SECURE=false
```

`.env` está ignorado por Git. No guardes allí credenciales compartidas; usa el gestor de secretos del equipo.

### Usuario inicial para verificar la aplicación

La aplicación no trae credenciales predeterminadas. Para la primera revisión crea un superusuario:

```bash
make superuser
```

En Windows: `.\.venv\Scripts\python.exe manage.py createsuperuser`.

El comando solicita **correo** y contraseña; no solicita nombre de usuario porque el correo es el identificador de acceso. Entra en `http://127.0.0.1:8000/accounts/login/` con esas credenciales. El superusuario es la opción más sencilla para verificar toda la interfaz y `http://127.0.0.1:8000/admin/`; no lo compartas ni lo uses como cuenta cotidiana.

Después de `make migrate` existen tres grupos para cuentas normales:

- `Analista`: consulta proveedores, planes, comparaciones e historial.
- `Operador`: incluye la consulta anterior y puede ver y solicitar el pipeline completo.
- `Administrador`: recibe todos los permisos de la aplicación, sin convertir la cuenta en superusuario.

Desde el admin, el superusuario puede crear otra cuenta y asignarle uno de esos grupos. `seed_demo` no crea usuarios ni contraseñas: solo crea un proveedor y dos fuentes de ejemplo deshabilitadas.

## 3. Procesos de desarrollo

La aplicación requiere dos procesos independientes:

Terminal 1, servidor web:

```bash
make dev
```

Terminal 2, scheduler:

```bash
make scheduler
```

En Windows PowerShell abre dos terminales y ejecuta respectivamente:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe manage.py run_scheduler
```

No abras un segundo scheduler: el lock local lo rechazará. Para comprobarlo sin dejar un proceso residente:

```bash
.venv/bin/python manage.py run_scheduler --once
```

### Detener los procesos

Si ejecutaste el flujo nativo de esta sección, sí: pulsa `Ctrl+C` una vez en la terminal de `make dev` y otra vez en la terminal de `make scheduler`. Espera a que cada comando devuelva el prompt; eso detiene servidor y scheduler sin borrar la base ni la evidencia.

Si también levantaste Mailpit, detenlo por separado:

```bash
docker compose stop mailpit
```

Si usaste el flujo Docker de la sección 7, no dependas de `Ctrl+C` porque `make docker-up` arranca en segundo plano; usa `make docker-down`. Este comando conserva los volúmenes. Evita `docker compose down -v`, que sí elimina los datos persistentes.

URLs habituales:

- Aplicación: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin/`
- Liveness: `http://127.0.0.1:8000/public/health`
- Readiness: `http://127.0.0.1:8000/public/ready`

## 4. Correo local

Por defecto los mensajes aparecen en la consola. Para inspeccionarlos con Mailpit:

```bash
docker compose --profile development up -d mailpit
```

Configura `.env`:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=127.0.0.1
EMAIL_PORT=1025
EMAIL_USE_TLS=false
```

La interfaz de Mailpit queda en `http://127.0.0.1:8025`. Detén solo ese servicio con `docker compose stop mailpit`.

## 5. Datos y fuentes de ejemplo

```bash
.venv/bin/python manage.py seed_demo
```

En Windows: `.\.venv\Scripts\python.exe manage.py seed_demo`.

Después de aplicar las migraciones también aparecen fuentes Google Maps deshabilitadas para Anfibius, Perseo y Siigo Contífico. Revisa sus URLs, autorización y límites antes de activar `enabled` y `schedule_enabled`.

Las fuentes se crean deshabilitadas y apuntan a un dominio ficticio. No las actives sin reemplazar la URL y revisar autorización, límites, selectores y pruebas offline. La metodología para implementar y probar un adaptador sin scheduler, base de datos ni red real está en [Agregar un proveedor](ADDING_A_PROVIDER.md).

La base local está en `data/market-watch.sqlite3`; `data/` está ignorado. Para una migración nueva:

```bash
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py migrate
.venv/bin/python manage.py makemigrations --check --dry-run
```

En Windows sustituye cada `.venv/bin/python` por `.\.venv\Scripts\python.exe`.

Revisa siempre la migración generada. `AUTH_USER_MODEL` no debe cambiar.

No reemplaces esta base para resolver un error de migración. Si la tarea exige recrearla, detén
ambos procesos y sigue el procedimiento con dos respaldos recuperables de
[Pipeline Django](../data/DJANGO_PIPELINE.md#regenerar-sqlite-de-forma-segura). Una base nueva no conserva
usuarios: vuelve a ejecutar `createsuperuser` después de verificar el backup.

## 6. Flujo diario

1. Ejecuta `make status` y lee `docs/PROGRESS.md`.
2. Activa `.venv` o usa siempre `.venv/bin/python`.
3. Trabaja en una unidad pequeña.
4. Ejecuta formato, lint y la prueba dirigida.
5. Ejecuta `make test`; usa `make test-playwright` solo para cambios del navegador.
6. Si cambió frontend, ejecuta `make assets` y comprueba que `src/static/dist/` se actualizó.
7. Antes de entregar, ejecuta `make verify` si también necesitas validar Docker.

Comandos rápidos:

```bash
make format
make lint
.venv/bin/python -m pytest tests/market/test_domain.py
make test
make test-playwright
make assets
```

Equivalentes principales en Windows PowerShell (el `Makefile` no es requisito):

```powershell
.\.venv\Scripts\python.exe -m ruff format src tests manage.py
.\.venv\Scripts\python.exe -m ruff check src tests manage.py
.\.venv\Scripts\python.exe -m pytest -m "not playwright"
.\.venv\Scripts\python.exe -m pytest -m playwright
$env:NODE_OPTIONS='--max-old-space-size=1536'
corepack pnpm --dir frontend build
```

Ninguna prueba consulta Internet. Las fixtures viven en `tests/fixtures/providers/`.

## 7. Desarrollo con Docker

El flujo nativo ofrece recarga más rápida. Para reproducir producción:

```bash
cp .env.example .env
# Ajusta SECRET_KEY y deja ALLOWED_HOSTS/CSRF para localhost.
make build
make docker-migrate
make docker-up
```

En Windows con Docker Desktop, `docker compose` conserva la misma sintaxis:

```powershell
Copy-Item .env.example .env
docker compose build
docker compose run --rm web python manage.py migrate
docker compose up -d web scheduler
```

La cuenta creada con `make superuser` pertenece solo a la base nativa. Para crear un usuario dentro de la base Docker usa, después de migrar:

```bash
docker compose run --rm web python manage.py createsuperuser
```

Comprueba `docker compose ps` y `http://127.0.0.1:8000/public/ready`. Los volúmenes Docker conservan SQLite y evidencia aunque ejecutes `docker compose down`.

```bash
make docker-logs
make docker-down
```

No uses `docker compose down -v` salvo que quieras borrar deliberadamente la base y demás volúmenes.

## 8. Persistencia y seguridad de los datos

El flujo nativo y Docker no comparten SQLite:

| Entorno | Base | Usuarios |
|---|---|---|
| Nativo (`make dev`) | `data/market-watch.sqlite3`, o la ruta indicada por `DATABASE_PATH` | Los creados con `make superuser` |
| Docker (`make docker-up`) | `/app/data/market-watch.sqlite3` dentro del volumen `sqlite-data` | Los creados con `docker compose run --rm web python manage.py createsuperuser` |
| Pytest (`make test`) | SQLite `:memory:` bajo `config.settings.test` | Datos temporales de cada prueba |

Cambiar entre el servidor nativo y el contenedor puede parecer una pérdida de usuarios, pero normalmente se está consultando otra base. Comprueba el origen nativo y los conteos sin mostrar correos:

```bash
.venv/bin/python manage.py shell -c "from django.conf import settings; from django.contrib.auth import get_user_model; print(settings.DATABASES['default']['NAME']); print('usuarios=', get_user_model().objects.count()); print('superusuarios=', get_user_model().objects.filter(is_superuser=True).count())"
docker compose ps --all
docker volume ls --filter name=sqlite-data
```

La auditoría de los comandos incluidos en el repositorio da este resultado:

- `make setup`, `make migrate`, `make dev`, `make scheduler`, `make assets` y `scripts/dev-bootstrap.sh --apply` no eliminan la base ni usuarios. El bootstrap tampoco sobrescribe un `.env` existente.
- `make test` y `make test-playwright` usan la base en memoria; no abren la base de desarrollo con la configuración predeterminada.
- `make build` solo construye imágenes. `make docs-check` consulta la configuración de Compose sin arrancar servicios.
- `make nginx-check` y `make deploy-check` pueden mostrar logs de un contenedor Nginx efímero; ese contenedor no monta `sqlite-data` ni la base nativa.
- `make docker-migrate`, `make docker-up` y `make docker-down` usan o conservan el volumen Docker. `make docker-down` no incluye `-v`.
- `scripts/deploy-production.sh --apply` sí modifica el esquema de producción mediante migraciones, pero antes crea un backup cuando detecta el servicio web activo; no borra la base.

Las operaciones destructivas no forman parte de las guías: `docker compose down -v`, `docker volume rm`, borrar `data/market-watch.sqlite3` o ejecutar `manage.py flush`. No las uses si deseas conservar datos. Antes de experimentar con persistencia nativa ejecuta `make backup`.

## 9. Diagnóstico

- `unable to open database file`: crea `data/` y comprueba permisos; `make migrate` lo hace.
- `database is locked`: confirma que solo hay un scheduler y que SQLite está en disco local, no NFS.
- assets 404: ejecuta `make assets`; en Docker reconstruye la imagen.
- Chromium ausente: `.venv/bin/playwright install chromium`.
- readiness 503: aplica migraciones y revisa acceso a SQLite.
- solicitud manual detenida: `run_scheduler --once` procesa una solicitud de cada cola, incluida la
  del pipeline completo. Revisa luego **Pipeline de mercado** y los logs del scheduler.

Consulta también [Uso de recursos](../operations/RESOURCE_USAGE.md), [Seguridad](../operations/SECURITY.md) y [Operación](../operations/OPERATIONS.md).
