# Producción desde cero

Esta guía levanta la aplicación web y **un solo scheduler** con Docker Compose. Linux con Nginx y
Certbot es la ruta canónica para un servidor desatendido. Windows puede ejecutar la misma imagen
con Docker Desktop; para publicarla debe añadirse en el mismo host un proxy inverso que termine TLS
(el ejemplo usa Caddy). Los volúmenes de SQLite, evidencia y media sobreviven a `docker compose
down`; nunca uses `docker compose down -v` en producción.

Las salidas mostradas son resumidas: nombres de contenedor, hashes y tiempos cambian en cada host.
Un comando sólo se considera exitoso cuando termina con código `0` y aparece el estado indicado.

## Antes de empezar

Necesitas un dominio apuntando al servidor, puertos 80/443 abiertos, espacio para imágenes y
backups, y un repositorio obtenido por el mecanismo aprobado por el equipo. Revisa además
[seguridad](SECURITY.md) y [operación/recuperación](OPERATIONS.md). SQLite debe vivir en disco local,
no en NFS o una carpeta sincronizada.

| Componente                      | Linux                           | Windows                                                                    |
| ------------------------------- | ------------------------------- | -------------------------------------------------------------------------- |
| Contenedores Linux y Compose v2 | Docker Engine                   | Docker Desktop con contenedores Linux                                      |
| Proxy HTTPS                     | Nginx + Certbot del host        | Proxy TLS del host; ejemplo Caddy                                          |
| Aplicador                       | `scripts/deploy-production.sh`  | `scripts\deploy-production.ps1`                                            |
| Uso recomendado                 | Servidor canónico y desatendido | Instalación controlada; depende del arranque de Docker Desktop y del proxy |

## Evaluar la producción localmente sin dominio ni HTTPS

> ESTA SECCION ES INFORMATIVA Y DEBE USARSE SOLO COMO REFERENCIA MIENTRAS SE SIGUEN LOS PASOS INDICADOS EN LAS SECCIONES **"Ruta Linux con Nginx"** O **"Ruta Windows con Docker Desktop"** SI SE UNA CONFIGURACIÓN MAS PERMISIVA EN PRODUCCIÓN.

El perfil `local-http` permite construir y ejecutar la misma imagen productiva en una máquina local
sin Nginx, dominio ni certificado. Es deliberadamente distinto del preflight normal: sólo acepta
`localhost` y `127.0.0.1`, mantiene la protección SSRF y no puede usarse para publicar el servicio
en una LAN o Internet. El perfil estricto sigue siendo el predeterminado.

Puedes partir de tu `.env` de desarrollo, pero debe contener una `SECRET_KEY` aleatoria de al menos
50 caracteres y estos valores:

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000
APP_BASE_URL=http://localhost:8000
SECURE_SSL_REDIRECT=false
SESSION_COOKIE_SECURE=false
CSRF_COOKIE_SECURE=false
SCRAPER_ALLOW_PRIVATE_HOSTS=false
```

`DEBUG=true` puede permanecer en ese archivo, pero la imagen productiva lo fuerza a `False`. Las
cookies no seguras sólo son aceptables porque Compose publica Gunicorn en `127.0.0.1`; no cambies
ese bind. Si prefieres navegar con `http://127.0.0.1:8000`, puedes usar esa misma dirección tanto en
`CSRF_TRUSTED_ORIGINS` como en `APP_BASE_URL`.

Linux:

```bash
scripts/deploy-production.sh --check --local-http
scripts/deploy-production.sh --apply --local-http
curl -fsS http://127.0.0.1:8000/public/ready
```

Windows PowerShell:

```powershell
.\scripts\deploy-production.ps1 -Check -LocalHttp
.\scripts\deploy-production.ps1 -Apply -LocalHttp
curl.exe -fsS http://127.0.0.1:8000/public/ready
```

Salida de éxito resumida:

```text
Configuración local HTTP válida. No es apta para exposición pública.
Release HASH saludable: web y scheduler activos.
{"status": "ready"}
```

El argumento puede ir antes o después de `--check`/`--apply` en Bash. `--apply --local-http`
mantiene backup, build, migración, scheduler y readiness; únicamente cambia el perfil de seguridad
y omite las validaciones Nginx/certificado. Para crear el usuario y detener el ensayo:

```bash
docker compose run --rm web python manage.py createsuperuser
docker compose stop scheduler web
```

Los comandos Docker son iguales en PowerShell. Los volúmenes Compose son independientes de los
archivos nativos del host: aunque `DATABASE_PATH=data/market-watch.sqlite3` provenga de tu `.env`,
dentro de la imagen se resuelve bajo `/app/data` y usa `sqlite-data`; no abre directamente
`data/market-watch.sqlite3` del host. `docker compose down` conserva esos datos, mientras que
`docker compose down -v` los elimina y no debe usarse.

Para volver a una configuración publicable, crea `.env` desde `.env.production.example`, configura
dominio/TLS y ejecuta el comando sin `--local-http`/`-LocalHttp`. No interpretes un check local
correcto como validación de producción pública.

## Ruta Linux con Nginx

Los comandos asumen Bash y se ejecutan desde la raíz del repositorio salvo que se indique lo
contrario. La configuración completa de Nginx, Certbot y renovación está en
[Despliegue con Nginx](DEPLOYMENT_NGINX.md).

### 1. Comprobar requisitos

```bash
docker compose version
nginx -v
certbot --version
git --version
```

Salida de éxito resumida:

```text
Docker Compose version v2.x.x
nginx version: nginx/1.x.x
certbot 2.x.x
git version 2.x.x
```

Si falta alguno, instálalo desde los repositorios y documentación de tu distribución antes de
continuar. No uses el paquete Compose v1 (`docker-compose`).

### 2. Obtener el código en una ruta estable

```bash
sudo mkdir -p /srv/market-watch
sudo chown "$USER":"$USER" /srv/market-watch
git clone URL_DEL_REPOSITORIO /srv/market-watch
cd /srv/market-watch
git status --short
```

La última orden no debe imprimir nada en una copia limpia. Sustituye `URL_DEL_REPOSITORIO` por la
URL autorizada; no pegues credenciales en el comando.

### 3. Crear y completar el entorno

```bash
cp .env.production.example .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

La última orden imprime una clave aleatoria larga. Edita `.env` y reemplaza `SECRET_KEY`, dominio,
correo y demás placeholders. Usa el mismo dominio en `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
`APP_BASE_URL`, `deploy/nginx-bootstrap.conf` y `deploy/nginx.conf`. No publiques ni confirmes
`.env` en Git. La [referencia de variables](../development/ENVIRONMENT_VARIABLES.md) describe cada
clave, tipo, ejemplo y diferencia entre rutas nativas y rutas del contenedor.

### 4. Ejecutar el preflight

```bash
scripts/deploy-production.sh --check
```

Salida de éxito:

```text
Configuración de despliegue válida.
```

El preflight valida secretos mínimos, políticas HTTPS, Compose, hosts de Nginx y sintaxis de ambas
configuraciones. Corrige cualquier error antes de aplicar.

### 5. Construir, migrar y arrancar

```bash
scripts/deploy-production.sh --apply
```

Salida final de éxito resumida:

```text
Construyendo release HASH...
Release HASH saludable: web y scheduler activos.
```

El script crea un backup si `web` ya estaba activo, construye una imagen que incluye Django,
cores, `frontend/` y las configuraciones iniciales, ejecuta migraciones y el seed idempotente del
pipeline, y levanta `web` y `scheduler`. Una salida `Pipeline inicial listo:
nightly-market@N` confirma que proveedores y fuentes quedaron sincronizados.

### 6. Activar HTTPS

Instala primero el virtual host HTTP, solicita el certificado y luego instala la configuración TLS:

```bash
sudo cp deploy/nginx-bootstrap.conf /etc/nginx/sites-available/market-watch
sudo ln -s /etc/nginx/sites-available/market-watch /etc/nginx/sites-enabled/market-watch
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/certbot -d market-watch.example.com
sudo cp deploy/nginx.conf /etc/nginx/sites-available/market-watch
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Sustituye el dominio y sigue los permisos/directorios exactos de
[activar Nginx TLS](DEPLOYMENT_NGINX.md#5-activar-nginx-tls). Las comprobaciones exitosas incluyen:

```text
nginx: configuration file ... test is successful
Congratulations! Your certificate ...
The dry run was successful.
```

### 7. Crear el primer superusuario

```bash
docker compose run --rm web python manage.py createsuperuser
```

Después de responder usuario/correo/contraseña, la salida exitosa es:

```text
Superuser created successfully.
```

Accede a `https://market-watch.example.com/admin/`. No reutilices esta cuenta para el scheduler ni
guardes su contraseña en `.env`.

### 8. Verificar aplicación, scheduler y backup

```bash
docker compose ps
docker compose ps --status running --services
curl -fsS https://market-watch.example.com/public/health
curl -fsS https://market-watch.example.com/public/ready
docker compose logs --no-color --tail=50 scheduler
docker compose exec -T web python manage.py backup_sqlite
sudo install -d -o "$USER" -g "$USER" /srv/backups/market-watch
docker compose cp web:/app/data/backups/market-watch-FECHA.sqlite3 /srv/backups/market-watch/
```

Salida de éxito resumida:

```text
web          running (healthy)
scheduler    running
{"status": "ok"}
{"status": "ready"}
/app/data/backups/market-watch-FECHA.sqlite3
```

Sustituye `FECHA` por el nombre que imprimió el comando anterior. Los dos servicios deben aparecer
una sola vez. Respalda también `media-data`; consulta
[backup externo y restauración](DEPLOYMENT_NGINX.md#7-backup-externo-y-restauración).

## Ruta Windows con Docker Desktop

Esta ruta ejecuta el runtime de producción en contenedores Linux. Requiere que Docker Desktop y el
proxy TLS arranquen después de reiniciar el equipo; valida esa automatización en el host antes de
considerarlo desatendido. Nginx/Certbot y los archivos `deploy/nginx*.conf` siguen siendo exclusivos
de Linux.

### 1. Comprobar requisitos

En PowerShell desde la raíz del repositorio:

```powershell
docker compose version
git --version
$PSVersionTable.PSVersion
```

Debes obtener Compose v2, Git y PowerShell 5.1 o 7+. Docker Desktop debe indicar que el engine de
contenedores Linux está activo.

### 2. Crear el entorno y generar el secreto

```powershell
Copy-Item .env.production.example .env
$Bytes = New-Object byte[] 64
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($Bytes)
[Convert]::ToBase64String($Bytes)
notepad .env
```

Copia la cadena generada a `SECRET_KEY` y reemplaza dominio, correo y placeholders. Mantén
`DEBUG=false`, cookies seguras, redirect HTTPS y `SCRAPER_ALLOW_PRIVATE_HOSTS=false`.

### 3. Validar y aplicar

```powershell
.\scripts\deploy-production.ps1 -Check
.\scripts\deploy-production.ps1 -Apply
```

También puedes usar el runner:

```powershell
.\Makefile.ps1 deploy-check
.\Makefile.ps1 deploy
```

Salidas finales de éxito:

```text
Configuración de despliegue Windows válida.
Release HASH saludable: web y scheduler activos.
```

El aplicador conserva la misma secuencia segura de Linux: backup previo si existe `web`, build,
migración, seed idempotente, arranque y readiness interno. No configura el firewall ni el proxy
público.

### 4. Añadir el proxy HTTPS del host

La aplicación sólo publica Gunicorn en `127.0.0.1:8000`; no cambies ese bind para exponerlo
directamente. Un ejemplo mínimo con Caddy instalado y autorizado por tu organización es un
`C:\market-watch\Caddyfile` con:

```caddyfile
market-watch.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Valida y arranca el proxy desde una consola elevada:

```powershell
caddy validate --config C:\market-watch\Caddyfile
caddy start --config C:\market-watch\Caddyfile
curl.exe -fsS https://market-watch.example.com/public/ready
```

Salida de éxito resumida:

```text
Valid configuration
Successfully started Caddy
{"status": "ready"}
```

Caddy debe poder usar 80/443 y resolver el dominio para emitir el certificado. Configura su inicio
automático siguiendo el mecanismo de servicio aprobado en el host. IIS/ARR u otro proxy son válidos
si terminan TLS, conservan `Host` y envían `X-Forwarded-Proto: https`.

### 5. Crear usuario y verificar

```powershell
docker compose run --rm web python manage.py createsuperuser
docker compose ps
docker compose ps --status running --services
curl.exe -fsS https://market-watch.example.com/public/health
curl.exe -fsS https://market-watch.example.com/public/ready
docker compose logs --no-color --tail=50 scheduler
docker compose exec -T web python manage.py backup_sqlite
New-Item -ItemType Directory -Force C:\Backups\market-watch | Out-Null
docker compose cp web:/app/data/backups/market-watch-FECHA.sqlite3 C:\Backups\market-watch\
```

Sustituye `FECHA` por el nombre impreso al crear el backup. Espera las mismas salidas del paso 8 de
Linux y respalda también el volumen de media fuera de Docker Desktop.

## Monitoreo habitual

Ejecuta estos comandos desde el directorio del proyecto; son iguales en Bash y PowerShell:

```text
docker compose ps
docker compose logs --no-color --tail=200 web scheduler
docker compose logs --no-color --since=30m scheduler
docker compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/public/ready', timeout=3); print('ready')"
```

La última orden debe imprimir `ready`. Desde fuera del servidor comprueba además la URL HTTPS. El
contenedor activo no demuestra por sí solo que el scheduler esté trabajando: revisa su heartbeat,
ejecuciones y cola en la administración, según [Operación](OPERATIONS.md#incidentes). Monitoriza
readiness, reinicios, espacio en disco, antigüedad de backups, errores del pipeline y expiración TLS.

## Detener, arrancar y reiniciar

Detención temporal, sin eliminar contenedores ni volúmenes:

```text
docker compose stop scheduler web
```

Arranque posterior y comprobación:

```text
docker compose up -d web scheduler
docker compose ps
```

Para retirar contenedores y red conservando los volúmenes:

```text
docker compose down
```

Una salida correcta contiene `Stopped`/`Removed` y termina con código `0`. Para recuperar el
servicio vuelve a ejecutar el aplicador o `docker compose up -d web scheduler`. Nunca añadas `-v`.
Detén siempre el scheduler antes que web para una restauración o mantenimiento de SQLite.

## Actualizar código, cores, Django o frontend

Todo el código se empaqueta en la misma imagen. El `Dockerfile` compila `frontend/`, ejecuta
`collectstatic` y copia Django y los cores; por eso no se actualiza un contenedor activo ni se edita
`src/static/dist/` manualmente.

Antes de desplegar revisa que `git status --short` no contenga trabajo local que pueda perderse y
obtén la release por el flujo aprobado. Después:

Linux:

```bash
git pull --ff-only
scripts/deploy-production.sh --check
scripts/deploy-production.sh --apply
docker compose ps
curl -fsS https://market-watch.example.com/public/ready
```

Windows:

```powershell
git pull --ff-only
.\scripts\deploy-production.ps1 -Check
.\scripts\deploy-production.ps1 -Apply
docker compose ps
curl.exe -fsS https://market-watch.example.com/public/ready
```

| Cambio                                        | Acción requerida                                                                |
| --------------------------------------------- | ------------------------------------------------------------------------------- |
| Python, Django, `scraping_core` u otros cores | Aplicador completo: rebuild, migración y recreate.                              |
| `frontend/`, CSS o JavaScript                 | Aplicador completo; el build regenera assets y `collectstatic`.                 |
| `requirements.lock`, `Dockerfile` o sistema   | Aplicador completo y revisión de logs/imagen.                                   |
| Modelos/migraciones                           | Backup previo obligatorio; revisa migraciones antes del aplicador.              |
| Sólo `.env`                                   | Ejecuta primero `-Check`/`--check` y luego el aplicador para recrear servicios. |
| Nginx Linux                                   | `sudo nginx -t && sudo systemctl reload nginx`; no requiere rebuild de imagen.  |
| Caddy Windows                                 | `caddy validate`, luego `caddy reload`; no requiere rebuild de imagen.          |

El éxito termina en `Release HASH saludable...`, ambos servicios aparecen activos y readiness HTTPS
devuelve `{"status": "ready"}`. Para rollback de imagen/esquema y restauración de SQLite no
improvises: sigue [rollback](DEPLOYMENT_NGINX.md#8-rollback) y
[backup/restauración](OPERATIONS.md#backup-y-restauración).

## Orden e invariantes

Las migraciones se ejecutan antes de actualizar servicios. Después se inicia `web` y exactamente un
`scheduler`; Compose espera el healthcheck web antes del scheduler. Nunca ejecutes migraciones
simultáneamente desde ambos contenedores, inicies tareas desde Gunicorn/Django, expongas el puerto
8000 a la red pública ni borres volúmenes durante despliegue o diagnóstico.
