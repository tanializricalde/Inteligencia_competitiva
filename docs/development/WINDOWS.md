# Desarrollo en Windows desde cero

Ejecuta los comandos desde la raíz del repositorio en PowerShell. Se admiten Python 3.12/3.13,
Node.js 20 con Corepack y SQLite local. Docker Desktop es opcional y debe usar Compose v2.

## 1. Comprobar y preparar el entorno

El runner de tareas no requiere GNU Make:

```powershell
.\Makefile.ps1 check
```

Instalación automatizada:

```powershell
.\scripts\dev-bootstrap.ps1 -Apply
```

El script no sobrescribe `.env`. Cuando falta, lo copia desde `.env.example`; luego crea `.venv`,
instala dependencias, compila assets, instala Chromium, migra, siembra el pipeline y valida Django.
Para omitir Chromium:

```powershell
.\scripts\dev-bootstrap.ps1 -Apply -SkipPlaywrightBrowser
```

Equivalente manual:

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
$env:NODE_OPTIONS='--max-old-space-size=1536'
corepack pnpm --dir frontend build
.\.venv\Scripts\python.exe -m playwright install chromium
New-Item -ItemType Directory -Force data
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_market_pipeline
.\.venv\Scripts\python.exe manage.py check
```

Cambia `SECRET_KEY` en `.env`; conserva el resto de valores de desarrollo sólo para localhost. En
[Variables de entorno](ENVIRONMENT_VARIABLES.md) se documentan rutas `C:/...`, tipos y diferencias
entre ejecución nativa y Docker Desktop.

## 2. Crear datos iniciales y usuario

El bootstrap anterior ya ejecutó `seed_market_pipeline`; repetirlo es seguro.

```powershell
.\Makefile.ps1 superuser
```

El acceso usa correo y contraseña. Para datos visuales opcionales:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo
```

## 3. Levantar Django y scheduler

Abre dos terminales PowerShell en la raíz.

Terminal 1:

```powershell
.\Makefile.ps1 dev
```

Terminal 2:

```powershell
.\Makefile.ps1 scheduler
```

Comprueba `http://127.0.0.1:8000/public/ready` y entra por
`http://127.0.0.1:8000/accounts/login/`. Pulsa `Ctrl+C` en cada terminal para detener los procesos;
la base `data\market-watch.sqlite3` se conserva.

## 4. Cambios en `frontend\`

Después de modificar `frontend\src\`:

```powershell
.\Makefile.ps1 assets
git status --short src/static/dist
```

El runner fija el límite de memoria, instala el lock de pnpm y construye con Vite. No edites
`src\static\dist\` directamente. Recarga el navegador; si el servidor no toma la salida nueva,
reinicia sólo la terminal `dev`. El scheduler no necesita reinicio por un cambio visual.

Con Docker Desktop, reconstruye la imagen para incorporar los assets:

```powershell
.\Makefile.ps1 build
.\Makefile.ps1 docker-up
```

## 5. Alternativa Docker Desktop

```powershell
Copy-Item .env.example .env
docker compose build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose up -d web scheduler
docker compose ps
```

Detén con `docker compose down`, nunca con `down -v` si quieres conservar datos. La base del volumen
Docker es distinta de la base nativa.

## 6. Validación habitual

```powershell
.\Makefile.ps1 lint
.\Makefile.ps1 test
.\Makefile.ps1 docs-check
```

PowerShell puede exigir una política temporal para scripts descargados:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Esto sólo afecta la terminal actual. Consulta [equivalencias de comandos](WINDOWS_LINUX.md) para
rutas y continuaciones de línea.

## 7. Producción desde Windows

Linux con Nginx/Certbot sigue siendo el servidor canónico, pero el runtime productivo también puede
levantarse con Docker Desktop y `scripts\deploy-production.ps1`. Windows debe aportar un proxy TLS
del host y asegurar el arranque automático del proxy y Docker Desktop; los archivos Nginx no se
ejecutan allí. Sigue el recorrido y sus límites en
[Producción desde cero](../operations/PRODUCTION.md#ruta-windows-con-docker-desktop).
