# Auditoría de módulos vigentes y heredados

Esta matriz delimita qué componentes participan en el pipeline canónico y cuáles se conservan
sólo por compatibilidad. La clasificación se basa en URLs, modelos, claves foráneas, comandos,
scheduler, Admin, pruebas y consultas del dashboard revisados el 19 de octubre de 2026.

## Matriz

| Superficie | Clasificación | Estado visible/automático | Evidencia y decisión |
|---|---|---|---|
| `pipeline.MarketSource`, perfiles/versiones, runs, artefactos, snapshots y catálogos canónicos | Vigente | Portal, Admin y scheduler | El orquestador ejecuta planes → características → reseñas y publica por proveedor. El dashboard consulta exclusivamente `ProviderRun` publicados y sus snapshots. |
| `market.Provider`, `DashboardPreset` y `DashboardSettings` | Vigente | Portal y Admin | Determinan identidad estable, ámbito REAL/DEMO, orden, filtros y branding. No son sustituibles por una lista frontend. |
| `pipeline.ScheduledJob`, cola manual canónica, `SchedulerHeartbeat` y notificaciones | Vigente | Portal/Admin/scheduler según permisos | Son el único camino automático soportado y ejecutan el pipeline versionado fuera del proceso web. |
| `scraping.ScrapeSource`, `ScrapeRun`, resultados y solicitudes manuales | Heredado con dependencia | Oculto del portal y Admin; no se agenda | Conserva datos, migraciones, servicios y comandos explícitos de transición. Ya no alimenta el dashboard canónico. |
| `scraping.ScheduleConfig` | Heredado con dependencia | Oculto; no lo lee el scheduler vigente | Sus campos aún son usados por servicios heredados y pruebas. El scheduler canónico usa `TIME_ZONE` y cada `ScheduledJob.timezone`. |
| `reviews.ReviewSource`, runs, resultados, solicitudes y agenda | Heredado con dependencia | Fuentes/runs ocultos; colas no agendadas | Las observaciones históricas conservan claves foráneas hacia estas entidades. La captura vigente usa `pipeline.MarketSource`. |
| `reviews.MarketReview`, observaciones y enriquecimientos | Heredado con dependencia | Sólo Admin/servicios históricos | Lista, detalle, resumen y exportación fueron migrados a `pipeline.ReviewSnapshot` en F59. Se conservan por relaciones, comandos y auditoría, no como fuente del portal. |
| `market.Plan`, snapshots y cambios | Heredado con dependencia | Historial y Admin conservados | Comparación fue migrada al pipeline en F59; `/plans/ID/history/` aún lee estas tablas. Retirarlas eliminaría ese reporte y evidencia relacionada. |
| `run_scrape`, `run_review_scrape` y `enrich_reviews` | Heredado con dependencia | Sólo invocación explícita por consola | Se conservan para diagnóstico/transición; no son invocados por la web ni el scheduler. |

No se encontró un conjunto clasificable como **Heredado sin dependencia** con evidencia suficiente
para borrado físico. Por ello no se eliminan modelos, tablas, migraciones, datos, servicios, templates
ni comandos en esta fase.

## Límites aplicados

- La inicialización sincroniza cada fuente sólo en `pipeline.MarketSource`; deja de crear o
  reactivar copias en `ScrapeSource` y `ReviewSource`.
- El scheduler procesa la cola manual canónica, jobs versionados, heartbeat, notificaciones y el
  enriquecimiento requerido por el reporte histórico. No consume solicitudes antiguas de captura.
- Las rutas de fuentes/runs antiguos no se publican y sus modelos operativos no aparecen en Admin.
- Comparación y reportes de reseñas consultan ya el esquema canónico. El historial de plan, Admin,
  comandos y servicios históricos justifican conservar las tablas antiguas hasta una retirada
  aprobada.

Para eliminar físicamente lo conservado falta demostrar, sobre un respaldo representativo, que no
hay relaciones ni datos que deban migrarse; reemplazar el historial de plan y servicios restantes;
retirar los comandos y pruebas de transición; y aprobar migraciones de esquema y una
estrategia de rollback. Hasta entonces, ocultar es reversible y no destruye información.

## Por qué puede faltar un competidor

La vista protegida **Todos** no lee `ScrapeSource`, `ReviewSource` ni sus runs. Un proveedor aparece
sólo si cumple simultáneamente:

1. `Provider.data_scope == "real"` y `Provider.is_active`;
2. existe un `ProviderRun` con estado `published` y `published_at`;
3. el run publicado contiene al menos un plan vigente y su `PlanSnapshot`;
4. los filtros temporales o un preset ordinario no lo excluyen.

Que una tabla heredada tenga filas o que una ejecución haya recuperado artefactos no equivale a
publicación canónica. Para diagnosticar, revise **Pipeline de mercado** y confirme el estado por
proveedor. En desarrollo puede sembrar catálogos e importar la muestra normalizada publicada:

```bash
.venv/bin/python manage.py seed_market_pipeline
.venv/bin/python manage.py import_normalized_dataset data/normalized --profile nightly-market --publish
```

En Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py seed_market_pipeline
.\.venv\Scripts\python.exe manage.py import_normalized_dataset data\normalized --profile nightly-market --publish
```

Estos comandos deben ejecutarse siguiendo el procedimiento de respaldo del entorno. Nunca se debe
cambiar un run a `published` manualmente: la publicación valida etapas y planes antes de hacerlo.
