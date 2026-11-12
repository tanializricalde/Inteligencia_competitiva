# Operación

## Procesos

Ejecuta `web` y exactamente un `scheduler`. Nunca arranques APScheduler desde WSGI/ASGI. El lock `scheduler.lock` evita duplicados locales; heartbeat y leases permiten diagnosticar/reanudar. Las migraciones son un paso explícito único antes del despliegue.

SQLite vive en volumen local, nunca NFS. Usa timeout de 20 s, foreign keys, WAL y transacciones cortas. Vigila tamaño, tiempo de escritura, `database is locked`, cola manual y antigüedad del heartbeat.

El trabajo nocturno nuevo se define con `ScheduledJob` y un `PipelineProfileVersion` publicado. El
scheduler ejecuta un único job por cron con barreras planes → características → reseñas; ya no
programa por separado los cron legados de planes y reseñas. Consulta comandos, reanudación y
publicación en [Pipeline persistente de Django](../data/DJANGO_PIPELINE.md).

## Backup y restauración

`make backup` usa la API `sqlite3.backup` y ejecuta `PRAGMA integrity_check`. Para destino explícito:

```bash
.venv/bin/python manage.py backup_sqlite --output /ruta/segura/market-watch.sqlite3
```

Para restaurar: detén web y scheduler, conserva la base actual fuera de la ruta activa, copia el backup verificado a `DATABASE_PATH`, ejecuta `PRAGMA integrity_check`, aplica `migrate` y arranca primero web, luego scheduler. Ensaya en un entorno aislado.

Para recrear una base vacía sin perder el original, sigue el procedimiento Linux/Windows de
[regeneración segura](../data/DJANGO_PIPELINE.md#regenerar-sqlite-de-forma-segura). La copia y el archivo
original se conservan; nunca se usa `flush` ni se elimina un volumen.

Las imágenes configurables del dashboard viven en `MEDIA_ROOT` y no están incluidas en el backup
SQLite. Respalda base y media como una misma unidad lógica. En una instalación local, copia la
carpeta indicada por `MEDIA_ROOT` a un destino versionado después del backup consistente; en
Compose, respalda el volumen `media-data`. Durante una restauración, recupera primero ambos
artefactos en una ventana sin escrituras y valida que las referencias de `DashboardSettings`
puedan abrirse. Si falta una imagen, la UI usa el fallback estático, pero eso no sustituye el
respaldo.

## Migración futura a PostgreSQL

Migra cuando haya más de una instancia web con escrituras sostenidas, bloqueos frecuentes, backups demasiado largos o necesidad de alta disponibilidad. Provisiona PostgreSQL, cambia `DATABASES` mediante configuración, migra esquema, exporta/importa datos con herramientas Django o ETL validado, compara conteos/hashes, cambia tráfico y conserva rollback. El dominio no contiene SQL SQLite.

## Releases y proxy TLS

La guía canónica Linux de instalación, TLS, actualización y rollback está en [Despliegue a producción con Nginx](DEPLOYMENT_NGINX.md). Antes de publicar, ejecuta `make deploy-check`; para desplegar usa `scripts/deploy-production.sh --apply`. En Windows se usa el aplicador PowerShell y un proxy TLS del host según [Producción desde cero](PRODUCTION.md#ruta-windows-con-docker-desktop). El servicio web queda enlazado a loopback y el proxy es el único punto de entrada público.

Tras cada release comprueba `docker compose ps`, readiness por HTTPS, logs de web/scheduler y que exista un único scheduler. Mantén al menos dos tags locales de imagen y backups copiados fuera del volumen. Valida `certbot renew --dry-run` al instalar TLS y monitoriza la fecha de expiración.


## Incidentes

- Scheduler detenido: revisa heartbeat, lock/PID y logs; `run_scheduler --once` valida sin quedar residente.
- Solicitud huérfana: los leases de 30 min vuelven a `pending`.
- Fuente fallida: revisa tipo sanitizado y evidencia limitada; conserva el último snapshot.
- Correo: inspecciona outbox, corrige SMTP y deja que el scheduler reintente.
- Artefacto ausente o alterado: compara ruta, tamaño y SHA-256 con `RunArtifact`; restaura desde
  backup o reejecuta la fuente. No elimines archivos conservando referencias en SQLite.

Los artefactos del pipeline no tienen purga automática. Define la retención según auditoría y
capacidad del entorno; respalda primero y retira coordinadamente filas `RunArtifact` y archivos
únicamente de ejecuciones que ya no puedan reanudarse ni deban investigarse.


## Reseñas legadas: transición

- Este flujo no aparece en portal ni Admin y el scheduler no consume sus solicitudes. Se conserva
  únicamente para diagnóstico/transición explícita mientras existan reportes que lean esas tablas.
- Ejecuta una fuente o competidor con `manage.py run_review_scrape --source ID` o `--provider codigo`; `--all` procesa todas las activas secuencialmente.
- `max_pages` y `max_reviews` limitan backfill. `last_cursor` reanuda lotes persistidos y `review_window` vuelve a observar registros recientes para detectar likes/respuestas.
- `ReviewScheduleConfig` y `run_review_scrape` se conservan para diagnóstico/transición, pero la
  agenda nocturna canónica usa `ScheduledJob` y `MarketSource` del pipeline unificado.
- No se crean nuevas `ManualReviewRequest` desde la web. No reactive esa cola ni cambie leases para
  intentar reparar un reporte.
- Reintenta una fuente sólo mediante el comando explícito después de revisar la configuración. No
  borres observaciones ni adelantes cursores manualmente sin backup.
- Procesa derivados con `manage.py enrich_reviews --limit 100`. Un fallo queda `failed`; una versión posterior del analizador puede crear otro enriquecimiento sin sobrescribir el anterior.
- Revisa los registros mediante una consola de diagnóstico autorizada; ya no existen esas pantallas
  operativas. Los logs no deben incluir texto completo, cookies ni payloads.
- Los adapters incluidos son fixtures offline; habilitarlos requiere `adapter_config.fixture_reviews`. No son conectores reales a Google.
