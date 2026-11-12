# Variables de entorno de Django y Compose

Esta referencia describe las claves de [.env.example](../../.env.example) y la adición productiva
de [.env.production.example](../../.env.production.example). Las plantillas contienen valores de
referencia: la aplicación lee el archivo `.env` de la raíz. Copia la plantilla apropiada y nunca
versiones `.env`, contraseñas ni claves reales.

## Cómo se carga la configuración

- `src/config/settings/base.py` carga `<raíz>/.env`. En ejecución nativa, una variable ya presente
  en el entorno del proceso tiene precedencia y no es reemplazada por el archivo.
- `manage.py` selecciona `config.settings.development`; WSGI/ASGI y la imagen Docker seleccionan
  `config.settings.production`. `APP_ENV` no selecciona el módulo de settings.
- Compose inyecta `.env` en `web` y `scheduler`. `WEB_PORT` se usa además al resolver
  `compose.yaml`, pero Django no lo lee.
- `.env.example` y `.env.production.example` no se cargan directamente. Son plantillas y contratos
  revisables; el nombre efectivo debe ser `.env`.
- Los cambios requieren reiniciar el proceso nativo. En Compose ejecuta de nuevo el aplicador para
  validar y recrear los servicios; editar `.env` no cambia un contenedor ya iniciado.

Los booleanos que Django reconoce como verdaderos son `true`, `1`, `yes`, `y`, `on` y `ok`, sin
distinguir mayúsculas. Cualquier otro texto se interpreta como falso. En las plantillas usa
exclusivamente `true` o `false`: los scripts de preflight productivo exigen esas formas exactas.
Las listas se separan con comas y no deben tener comas dentro de un elemento.

En desarrollo ninguna clave es formalmente obligatoria porque los settings comunes ofrecen
defaults, pero usar la clave insegura por defecto no es apropiado para sesiones que quieras
conservar. El preflight de producción sí exige valores no vacíos para `SECRET_KEY`, `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, `APP_BASE_URL` y `DATABASE_PATH`, además de las políticas seguras indicadas
en las tablas. Mantener todas las claves de la plantilla reduce diferencias entre hosts.

## Entorno, seguridad y URLs

| Variable | Tipo y valor de desarrollo | Explicación y ejemplos válidos |
| --- | --- | --- |
| `APP_ENV` | Texto; `development` | Etiqueta operativa. `development` y `production` son ejemplos convencionales, pero hoy no cambian los settings. El entrypoint determina el módulo efectivo. |
| `SECRET_KEY` | Texto secreto; la plantilla contiene un placeholder | Firma sesiones y tokens de Django. En producción es obligatoria, no puede contener los placeholders conocidos y el preflight exige al menos 50 caracteres. Genera una nueva con `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`; no copies la salida a documentación o Git. |
| `DEBUG` | Booleano; `true` | Expresa la intención del entorno y el preflight exige `false` en producción. Los módulos incluidos fuerzan `True` en desarrollo y `False` en producción/pruebas, de modo que cambiar sólo esta variable no cambia ese comportamiento. |
| `ALLOWED_HOSTS` | Lista de hosts; `localhost,127.0.0.1` | Hosts que Django acepta en `Host`, sin esquema ni ruta. Producción: `market-watch.example.com`; varios: `app.example.com,admin.example.com`. El preflight prohíbe `*`. Para un puerto local no añadas `:8000`. |
| `CSRF_TRUSTED_ORIGINS` | Lista de orígenes URL; `http://localhost:8000` | Orígenes autorizados para peticiones inseguras. Cada valor incluye esquema y, si aplica, puerto, pero no ruta: `http://127.0.0.1:8000` o `https://market-watch.example.com`. Producción exige HTTPS. |
| `APP_BASE_URL` | URL absoluta; `http://localhost:8000` | Base incluida en enlaces de notificaciones. No añade automáticamente hosts ni orígenes CSRF. Ejemplo productivo: `https://market-watch.example.com`; evita una barra final. |
| `APP_TIME_ZONE` | Zona IANA; `America/Lima` | Zona usada por Django para presentación y trabajos programados. Ejemplos: `UTC`, `America/Guayaquil`, `America/Lima`. No uses abreviaturas ambiguas como `EST`. La zona IANA es igual en Linux y Windows porque la interpreta Python. |
| `SESSION_COOKIE_SECURE` | Booleano; `false` | Solicita cookies de sesión sólo por HTTPS. El preflight público exige `true`; `--local-http` exige `false` para permitir login por HTTP. En runtime productivo queda seguro salvo que Compose reciba la marca interna del argumento local. |
| `CSRF_COOKIE_SECURE` | Booleano; `false` | Solicita la cookie CSRF sólo por HTTPS. El preflight público exige `true`; `--local-http` exige `false`. En runtime productivo queda seguro salvo durante ese perfil local explícito. |
| `SECURE_SSL_REDIRECT` | Booleano; `false` | En producción pública redirige HTTP a HTTPS, salvo health/readiness. El preflight público exige `true`; `--local-http` exige `false` y desactiva el redirect mediante una marca interna. Desarrollo no lee esta clave porque usa otro módulo. |
| `SECURE_HSTS_SECONDS` | Entero no negativo; `3600` | Duración de HSTS en segundos, sólo en producción. `0` desactiva HSTS; `3600` es el inicio conservador. Aumenta gradualmente después de verificar HTTPS. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | Booleano; `false` | Extiende HSTS a todos los subdominios, sólo en producción. Usa `true` únicamente si todos funcionan permanentemente por HTTPS. |
| `SECURE_HSTS_PRELOAD` | Booleano; `false` | Añade la directiva HSTS preload, sólo en producción. No registra el dominio por sí sola. Requiere cumplir previamente los requisitos del navegador y normalmente `INCLUDE_SUBDOMAINS=true`. |

## Persistencia y rutas

| Variable | Tipo y valor de desarrollo | Explicación y ejemplos válidos |
| --- | --- | --- |
| `DATABASE_PATH` | Ruta de archivo; `data/market-watch.sqlite3` | Archivo SQLite. Nativo Linux: `/srv/market-watch-data/market-watch.sqlite3`; Windows: `C:/market-watch/data/market-watch.sqlite3`. En Compose usa `/app/data/market-watch.sqlite3` para conservarlo en `sqlite-data`. No uses NFS ni carpetas sincronizadas. |
| `PIPELINE_ARTIFACT_ROOT` | Ruta de carpeta; `data/pipeline` | Raíz privada de artefactos importables y reanudables. Ejemplo Windows nativo: `C:/market-watch/data/pipeline`. En Compose debe permanecer bajo `/app/data`, por ejemplo `/app/data/pipeline`, para usar el volumen persistente. |
| `MEDIA_ROOT` | Ruta de carpeta; `media` | Archivos subidos, incluida la imagen configurable del dashboard. Ejemplo Linux nativo: `/srv/market-watch-media`; Windows: `C:/market-watch/media`. En Compose usa `/app/media`, respaldado por `media-data`. No es el directorio de assets frontend. |
| `SCRAPER_EVIDENCE_DIR` | Ruta de carpeta; `evidence` | Evidencia técnica saneada de providers/navegador. Ejemplos nativos: `/srv/market-watch-evidence` o `C:/market-watch/evidence`; en Compose usa `/app/evidence`, asociado a `evidence-data`. No debe ser público ni contener cookies. |

Las rutas relativas se resuelven respecto del directorio de trabajo del proceso. Los comandos
documentados parten de la raíz, por eso `data/...`, `media` y `evidence` funcionan en desarrollo.
Para Windows se recomiendan barras `/` incluso en `.env`; Python acepta `C:/ruta/archivo` y así se
evitan ambigüedades con barras invertidas. Si hay espacios, usa comillas dobles, por ejemplo
`MEDIA_ROOT="C:/Market Watch/media"`.

Las rutas Docker siempre pertenecen al filesystem Linux del contenedor, también cuando Docker
Desktop corre en Windows. No coloques `C:\...` en el `.env` consumido por los contenedores. Cambiar
una ruta `/app/data`, `/app/evidence` o `/app/media` por otra no montada puede dejar datos fuera de
los volúmenes y perderlos al reemplazar el contenedor.

## Correo y notificaciones

| Variable | Tipo y valor de desarrollo | Explicación y ejemplos válidos |
| --- | --- | --- |
| `EMAIL_BACKEND` | Ruta Python; `django.core.mail.backends.console.EmailBackend` | Backend Django. Consola imprime el mensaje sin enviarlo. Producción SMTP: `django.core.mail.backends.smtp.EmailBackend`. Para pruebas manuales con Mailpit también se usa SMTP. |
| `EMAIL_HOST` | Host; `localhost` | Servidor SMTP sin esquema ni puerto. Ejemplos: `127.0.0.1`, `smtp.example.com`. Se ignora con el backend de consola. |
| `EMAIL_PORT` | Entero; `1025` | Puerto SMTP. Mailpit suele usar `1025`; STARTTLS suele usar `587`. Debe corresponder al proveedor. |
| `EMAIL_HOST_USER` | Texto; vacío | Usuario SMTP. Puede quedar vacío en consola o Mailpit sin autenticación. Ejemplo productivo: `mailer@example.com`. |
| `EMAIL_HOST_PASSWORD` | Texto secreto; vacío | Contraseña/token SMTP. Es obligatoria sólo si el servidor autentica. No uses el placeholder productivo ni la registres en logs/Git. |
| `EMAIL_USE_TLS` | Booleano; `false` | Activa STARTTLS en el backend SMTP. Ejemplo habitual: puerto `587` con `true`; Mailpit local usa `1025` con `false`. No equivale a SMTP implícito/SMTPS del puerto 465: este proyecto no expone `EMAIL_USE_SSL`. |
| `DEFAULT_FROM_EMAIL` | Dirección o nombre + dirección; `noreply@example.test` | Remitente técnico de notificaciones. Producción: `noreply@example.com`. El servidor SMTP debe autorizarlo; el nombre visible de la aplicación se obtiene de la configuración central. |

Con el backend de consola, host, puerto, usuario, contraseña y TLS no provocan conexiones SMTP. Si
cambias a SMTP, valida el conjunto completo y envía primero un mensaje de prueba sin destinatarios
reales. Usa el gestor de secretos aprobado cuando la contraseña contenga caracteres difíciles de
representar o cuando el host permita inyección segura; no añadas comentarios al final de una línea
de secreto.

## Scraping y límites de red

| Variable | Tipo y valor de desarrollo | Explicación y ejemplos válidos |
| --- | --- | --- |
| `SCRAPER_USER_AGENT` | Texto; `MarketWatch/0.1 (+mailto:ops@example.test)` | Identifica solicitudes HTTP/navegador. Usa un producto, versión y contacto válido autorizado, por ejemplo `MarketWatch/1.0 (+mailto:ops@example.com)`. No suplantes un navegador o tercero. |
| `SCRAPER_MAX_RESPONSE_BYTES` | Entero positivo; `5000000` | Límite máximo de respuesta para adapters HTTP que lo consumen. `5000000` equivale aproximadamente a 5 MB decimales. Un número inválido impide iniciar settings; uno demasiado grande aumenta memoria/riesgo. |
| `SCRAPER_ALLOW_PRIVATE_HOSTS` | Booleano; `false` | Permite destinos loopback/red privada en la validación SSRF. Conserva `false` en producción; ambos aplicadores lo exigen. `true` sólo es apropiado en pruebas locales controladas con fixtures/servidores propios. |

## Puerto publicado por Compose

| Variable | Tipo y valor productivo | Explicación y ejemplos válidos |
| --- | --- | --- |
| `WEB_PORT` | Entero de puerto; `8000` | Sólo Compose: publica `127.0.0.1:WEB_PORT` hacia Gunicorn `:8000`. Ejemplos: `8000`, `8080` si está libre. No cambia el puerto interno ni debe exponerse en `0.0.0.0`; el proxy TLS accede por loopback. No aparece en `.env.example` porque el desarrollo nativo usa `runserver` directamente. |

Compose también declara `ALLOW_INSECURE_LOCAL_HTTP`, una marca interna que no pertenece a las
plantillas ni debe agregarse manualmente a `.env`. Los aplicadores siempre la sobrescriben:
`false` en el flujo normal y `true` sólo al recibir `--local-http`/`-LocalHttp`. Los settings
productivos usan esa marca para desactivar temporalmente redirect y cookies seguras en loopback;
sin ella permanecen seguros incluso si un `.env` de desarrollo contiene valores `false`.

## Ejemplos mínimos por sistema

Desarrollo nativo Linux:

```dotenv
DATABASE_PATH=data/market-watch.sqlite3
PIPELINE_ARTIFACT_ROOT=data/pipeline
MEDIA_ROOT=media
SCRAPER_EVIDENCE_DIR=evidence
APP_BASE_URL=http://localhost:8000
```

Desarrollo nativo Windows:

```dotenv
DATABASE_PATH=C:/market-watch/data/market-watch.sqlite3
PIPELINE_ARTIFACT_ROOT=C:/market-watch/data/pipeline
MEDIA_ROOT=C:/market-watch/media
SCRAPER_EVIDENCE_DIR=C:/market-watch/evidence
APP_BASE_URL=http://localhost:8000
```

Producción Compose en Linux o Docker Desktop:

```dotenv
DATABASE_PATH=/app/data/market-watch.sqlite3
PIPELINE_ARTIFACT_ROOT=/app/data/pipeline
MEDIA_ROOT=/app/media
SCRAPER_EVIDENCE_DIR=/app/evidence
WEB_PORT=8000
```

## Validación y diagnóstico

Desarrollo Linux:

```bash
.venv/bin/python manage.py check
```

Desarrollo Windows:

```powershell
.\.venv\Scripts\python.exe manage.py check
```

Producción Linux o Windows, respectivamente:

```bash
scripts/deploy-production.sh --check
```

```powershell
.\scripts\deploy-production.ps1 -Check
```

Evaluación local de la imagen productiva por HTTP:

```bash
scripts/deploy-production.sh --check --local-http
```

```powershell
.\scripts\deploy-production.ps1 -Check -LocalHttp
```

Este perfil requiere una clave fuerte, loopback, cookies/redirect HTTP desactivados y
`SCRAPER_ALLOW_PRIVATE_HOSTS=false`; no valida Nginx ni certificado. El procedimiento completo está
en [Producción local por HTTP](../operations/PRODUCTION.md#evaluar-la-producción-localmente-sin-dominio-ni-https).

Un error de conversión al arrancar suele indicar un entero o booleano inválido. Un `DisallowedHost`
apunta a `ALLOWED_HOSTS`; un rechazo CSRF, a que el origen completo no está en
`CSRF_TRUSTED_ORIGINS`; redirecciones infinitas detrás del proxy indican que falta
`X-Forwarded-Proto: https`. Antes de investigar Django, confirma también que estás editando el
`.env` de la raíz y reiniciaste el proceso o recreaste los contenedores.
