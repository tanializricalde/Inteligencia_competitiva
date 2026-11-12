# Pipeline persistente de Django

## Propósito

`apps.pipeline` es la fuente operativa de verdad para las ejecuciones nuevas. Conserva por
separado identidades estables, observaciones, precios, evidencia de características, valores
canónicos, reseñas, calidad y artefactos. Las tablas históricas de `market`, `scraping` y `reviews`
siguen disponibles temporalmente para las pantallas legadas, pero el scheduler nocturno nuevo no
escribe en ellas.

La CLI independiente continúa usando archivos y no requiere Django. Ambos caminos comparten
`scraping_core`, `data_cleaning`, `data_transformation` y los mappers públicos de
`data_pipeline.scraping_schemas`.

## Preparación inicial

Linux:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_market_pipeline
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_market_pipeline
```

El seed es idempotente. Lee `config.example.toml` y
`feature_rules/feature-equivalence.example.json`, crea fuentes sin secretos, cuatro versiones de
configuración publicadas, el perfil `nightly-market` y el job de las 02:00 en `America/Lima`. La
fuente declarativa crea iDrix, Anfibius, Perseo y Siigo con sus fuentes canónicas activas;
`competidor_demo` no se convierte en fuente operativa. No crea ni reactiva fuentes de los módulos
de ingesta heredados. Si cambia el contenido versionado, el seed crea y activa versiones nuevas en
vez de modificar las ya publicadas.

Los recorridos soportados (`make migrate`, `Makefile.ps1 migrate`, ambos bootstrap y ambos scripts
de despliegue) ejecutan migración y seed en ese orden. Llamar directamente a `manage.py migrate`
sólo modifica el esquema; ejecuta luego `seed_market_pipeline` si eliges el recorrido manual.

## Configuraciones versionadas

Importar nunca publica:

```bash
.venv/bin/python manage.py validate_pipeline_config feature_rules/feature-equivalence.example.json --stage feature_equivalence
.venv/bin/python manage.py import_pipeline_config feature_rules/feature-equivalence.example.json --code feature-equivalence-v2 --stage feature_equivalence --config-version 2
.venv/bin/python manage.py publish_pipeline_config --code feature-equivalence-v2 --config-version 2
.venv/bin/python manage.py export_pipeline_config --code feature-equivalence-v2 --config-version 2 --output /tmp/feature-equivalence-v2.json
```

En PowerShell sustituye `.venv/bin/python` por `.\.venv\Scripts\python.exe` y usa, por ejemplo,
`--output .\tmp\feature-equivalence-v2.json`. Una ejecución fija una versión publicada concreta;
cambiar el perfil activo no altera ejecuciones anteriores. Contraseñas, tokens, cookies y claves
de API son rechazados y deben venir del entorno o de un gestor de secretos.

## Ejecución

### Desde Django

Abre **Pipeline de mercado** en el menú lateral (`/pipeline-runs/`) y pulsa **Ejecutar pipeline
completo**. La acción necesita `pipeline.add_pipelinerun`, registra un `PipelineRun` pendiente y
regresa inmediatamente; no hace scraping en el proceso web. El scheduler toma la solicitud en su
siguiente ciclo y ejecuta planes → características → reseñas. La misma pantalla muestra fuentes,
activación y estados recientes. Los miembros del grupo **Operador** reciben los permisos de vista y
ejecución después de `migrate`; un superusuario también puede usarla.

Las pantallas y colas de captura anteriores están ocultas y el scheduler no las consume. Sus
modelos se conservan por relaciones y reportes históricos; consulte la
[auditoría de módulos](LEGACY_MODULE_AUDIT.md).

### Desde la terminal

Revisar orden y fuentes sin scraping ni escrituras de negocio:

```bash
.venv/bin/python manage.py run_market_pipeline --profile nightly-market --dry-run
```

Ejecutar todo, siempre secuencial:

```bash
.venv/bin/python manage.py run_market_pipeline --profile nightly-market
```

Acotar proveedores, no publicar o reanudar:

```bash
.venv/bin/python manage.py run_market_provider --profile nightly-market --provider anfibius
.venv/bin/python manage.py run_market_pipeline --profile nightly-market --provider siigo_ec --no-publish
.venv/bin/python manage.py run_market_pipeline --profile nightly-market --resume-run UUID
```

`run_market_stage` es diagnóstico y nunca publica. `features` y `reviews` requieren
`--resume-run` para comprobar sus dependencias y reutilizar artefactos de la misma ejecución:

```bash
.venv/bin/python manage.py run_market_stage --profile nightly-market --provider anfibius --stage plans
.venv/bin/python manage.py run_market_stage --profile nightly-market --provider anfibius --stage features --resume-run UUID
```

En Windows los argumentos son iguales; cambia únicamente el binario y, cuando corresponda, los
separadores de rutas.

El orden programado es una barrera global:

1. planes de todos los proveedores;
2. características de todos los proveedores;
3. reseñas de todos los proveedores.

Dentro de cada grupo se respeta `execution_order`; nunca hay dos fuentes activas simultáneamente.
Los reintentos son por fuente. Una dependencia fallida produce `skipped`, otro proveedor continúa
y `--resume-run` conserva cada `SourceRun` exitoso. Al reanudar, una fuente fallida obtiene otra
ronda de `max_attempts`; `attempt_count` sigue siendo acumulativo para auditoría. Sólo un
`ProviderRun` completo se publica.
Al terminar, el orquestador encola en el outbox existente un evento idempotente por proveedor:
`DATA_CHANGED` si se publicó o `SCRAPE_FAILED` si quedó incompleto. El job periódico de
notificaciones entrega esos eventos sin acoplar SMTP a la transacción de importación/publicación.

### Diagnóstico de fallos por proveedor

En **Ejecuciones recientes**, despliega el texto rojo bajo el proveedor para ver el error completo.
El resumen prioriza el primer fallo concreto de fuente con el formato
`etapa/fuente: TipoDeError: detalle`; si una ejecución anterior no guardó `error_summary`, la vista
lo reconstruye desde `SourceRun` o `StageRun`. Por ello una fila antigua de Anfibius que sólo decía
**Fallida** mostrará el diagnóstico almacenado sin repetir el scraping.

`DatasetImportError: Booleano inválido: 0.0` o `1.0` era un error del límite ORM, no del adapter:
al reconstruir JSON, pandas puede promover una columna booleana anulable a flotante. El importador
acepta ahora exclusivamente los números binarios exactos `0`, `1`, `0.0` y `1.0`, además de las
representaciones booleanas ya admitidas; sigue rechazando valores ambiguos como `0.5`. La CLI no
mostraba el problema porque serializa los contratos a archivos y no ejecuta la importación Django.

## Importar archivos normalizados

La carpeta debe contener `plans.csv`, `features.csv` y `reviews.csv`; puede incluir
`quality-report.json`. `features-wide.csv` se ignora deliberadamente:

```bash
.venv/bin/python manage.py import_normalized_dataset data/normalized --profile nightly-market --publish
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py import_normalized_dataset .\data\normalized --profile nightly-market --publish
```

`--provider` limita el reproceso sin editar las publicaciones de otros competidores. Después de
actualizar reglas de equivalencia, primero ejecuta `seed_market_pipeline` para crear una versión
inmutable nueva y luego reprocesa. Por ejemplo, para promover `centro_de_costos` y republicar sólo
Perseo desde los archivos locales:

Linux con Docker Compose:

```bash
docker compose run --rm web python manage.py seed_market_pipeline
docker compose run --rm --volume "$(pwd)/data/normalized:/input:ro" web python manage.py import_normalized_dataset /input --profile nightly-market --provider perseo --publish
```

Windows PowerShell con Docker Desktop:

```powershell
docker compose run --rm web python manage.py seed_market_pipeline
docker compose run --rm --volume "${PWD}/data/normalized:/input:ro" web python manage.py import_normalized_dataset /input --profile nightly-market --provider perseo --publish
```

La imagen debe contener previamente el código y las reglas actualizados. El bind mount es de sólo
lectura porque `data/` no se copia a la imagen productiva. La publicación anterior se conserva como
histórico; el dashboard selecciona el nuevo corte sólo si el reproceso termina y se publica.

Sin `--publish`, la ejecución queda completa pero no reemplaza la vista vigente. Para publicar
posteriormente:

```bash
.venv/bin/python manage.py publish_pipeline_run UUID
```

## Snapshot de recuperación de Anfibius

La migración `pipeline.0003_seed_anfibius_recovery_snapshot` incorpora una captura histórica REAL
de Anfibius porque su página editorial dejó de exponer la estructura observada por el adapter. Se
aplica mediante el flujo normal de migraciones:

Linux:

```bash
.venv/bin/python manage.py migrate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

La captura procede de `data/normalized/` y conserva 3 planes, 15 características fuente, 186
valores normalizados y las métricas de 50 reseñas. No contiene precios porque la captura original
no los obtuvo. Los nombres, textos, respuestas e IDs externos de las reseñas se excluyeron antes
de empaquetar el fixture; sólo se conservan calificación, sentimiento, país, plataforma y estado de
respuesta.

La ejecución queda marcada como `reprocess`, `published` y `data_scope=real`, con la fecha fija de
la captura del 5 de octubre de 2026. Por eso sirve como último snapshot válido cuando las nuevas
ejecuciones fallan, pero nunca desplaza una publicación posterior. La migración no desactiva la
fuente: cuando el adapter vuelva a funcionar, una ejecución publicada más reciente la sustituirá
automáticamente en el dashboard. Las ejecuciones fallidas posteriores pueden seguir apareciendo en
**Pipeline de mercado** sin invalidar esta publicación.

El fixture inmutable vive junto a la migración porque `data/` no forma parte de la imagen Docker.
Su generador reproducible es `scripts/generate_anfibius_recovery_fixture.py`; no debe regenerarse
después de desplegar la migración. Una captura futura debe usar otra versión de fixture y otra
migración.

## Consulta

La capa de aplicación ofrece últimos planes/reseñas publicados, historia de precios, comparación
de valores, estadísticas y estados. La matriz dinámica autenticada está en:

```text
GET /pipeline/api/features-wide/
GET /pipeline/api/features-wide/?at=2026-10-05T21:00:00Z
```

`at` selecciona, por proveedor, la publicación más reciente no posterior a esa fecha. La respuesta
incluye `columns` y `rows`; no existe una tabla SQLite con columnas dinámicas.

## Artefactos y trazabilidad

Los archivos viven bajo `PIPELINE_ARTIFACT_ROOT` (por defecto `data/pipeline`) con rutas relativas:

```text
<run_id>/<provider>/<stage>/...
```

`RunArtifact` conserva ruta, SHA-256 y tamaño. La escritura usa temporal y reemplazo atómico. Los
valores fallback enlazan la fila fuente exacta; reglas y derivados conservan por ahora el conjunto
de filas candidatas del plan y lo declaran como `trace_scope=plan_candidate_rows`. Ésta es una
limitación explícita hasta que el motor exponga provenance por aporte.

La retención no se automatiza todavía. Antes de retirar artefactos antiguos, confirma que su
`PipelineRun` ya no sea necesario para auditoría o reanudación, crea un backup y elimina en una
misma ventana operativa tanto el archivo como su `RunArtifact`; no dejes referencias rotas. Para
diagnóstico compara tamaño y SHA-256 con el registro, revisa `SourceRun.error_type/error_message`
y conserva el artefacto fallido hasta cerrar el incidente.

## Incorporar una fuente o proveedor

1. Implementa y prueba el adapter en el core puro con un fixture local sanitizado.
2. Registra el proveedor mediante su `Provider.code` estable y crea un `MarketSource` por tipo de
   dato; `adapter_key` identifica código, no al competidor.
3. Define `execution_order`, obligatoriedad, límites y reintentos sin secretos en `settings_json`.
4. Importa/publica una versión nueva de la configuración de extracción y fija esa versión en un
   borrador nuevo de `PipelineProfileVersion`; nunca edites una versión publicada.
5. Ejecuta `run_market_provider --no-publish`, revisa artefactos/calidad y publica sólo después de
   validar conteos, identidad e idempotencia.

Para nuevas equivalencias sigue [Reglas de equivalencia](FEATURE_EQUIVALENCE_RULES.md#extender-y-probar),
importa el JSON resultante como otra `PipelineConfigVersion` y crea/publica una versión de perfil
que la referencie. Las características provider-scoped desconocidas siguen siendo dinámicas y no
requieren migración.

## Regenerar SQLite de forma segura

Detén `runserver` y `run_scheduler`. Nunca uses `flush`, borres la base ni ejecutes
`docker compose down -v`. Primero crea y verifica un respaldo:

Linux:

```bash
.venv/bin/python manage.py backup_sqlite --output data/backups/market-watch-pre-pipeline.sqlite3
mv data/market-watch.sqlite3 data/backups/market-watch-original.sqlite3
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed_market_pipeline
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py backup_sqlite --output .\data\backups\market-watch-pre-pipeline.sqlite3
Move-Item .\data\market-watch.sqlite3 .\data\backups\market-watch-original.sqlite3
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py seed_market_pipeline
```

Usa nombres fechados y comprueba que el destino no exista. Después valida `manage.py check`,
`manage.py makemigrations --check --dry-run`, `PRAGMA integrity_check` y conteos. La regeneración
elimina las cuentas de la base activa; crea de nuevo el superusuario con `createsuperuser` si lo
necesitas. El original y el backup permiten recuperación.

## Limitaciones vigentes

- las fechas reales de publicación/respuesta permanecen nulas cuando el provider no las obtiene;
  `timestamp_ingesta` no se interpreta como publicación;
- SQLite requiere un host y un único scheduler/escritor del pipeline;
- las tablas históricas legadas se conservan por compatibilidad y auditoría, pero sus pantallas y
  ejecución automática están retiradas; el dashboard y la pantalla de ejecución canónica usan
  `MarketSource`/`ProviderRun`;
- el scraping real depende de estructura, disponibilidad y condiciones de cada fuente; los tests
  usan fixtures y no evaden autenticación, CAPTCHA ni restricciones.
