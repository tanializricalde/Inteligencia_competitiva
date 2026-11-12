# Matriz de pruebas del pipeline persistente

| Área | Caso verificable | Estado |
| --- | --- | --- |
| Migraciones | Crear SQLite temporal y aplicar todas las migraciones | Aprobada: migraciones completas sobre `/tmp/dstools-pipeline-migrations.sqlite3` |
| Migraciones | `makemigrations --check --dry-run` no detecta cambios | Aprobada |
| Integridad | Constraints de scope/provider y valor tipado | Aprobada: validación de modelo y constraint SQLite |
| Configuración | Hash canónico, borrador, publicación e inmutabilidad | Aprobada: hash, secretos e inmutabilidad cubiertos |
| Configuración | Perfil fija versiones exactas por etapa | Aprobada: una etapa no puede añadirse a una versión publicada |
| Transformación | Generar `feature-values` tipado antes de la vista ancha | Aprobada: 1.674 filas reales, 14 columnas |
| Transformación | Vista ancha se reconstruye desde valores largos | Aprobada: 27 filas/64 columnas |
| Transformación | Regla, fallback, default y derivado conservan origen | Aprobada: pruebas unitarias y auditoría real |
| Importación | Plan estable recibe snapshots y precios históricos | Aprobada |
| Importación | Característica dinámica no exige migración | Aprobada: definición provider-scoped creada en importación |
| Importación | Evidencia larga se conserva y enlaza al valor | Aprobada: fallback exacto y candidatos explícitos para regla/derivada |
| Importación | Reseña estable admite observaciones posteriores | Aprobada |
| Importación | Reimportar artefactos no duplica identidades/snapshots | Aprobada |
| Calidad | Rating inválido, colisión y discrepancia generan incidencia | Aprobada: validaciones de rating/precio cubiertas por core y colisión importada como incidencia |
| Scheduler | Orden exacto planes→features→reviews | Aprobada: secuencia exacta de siete invocaciones |
| Scheduler | Proveedores y fuentes se ejecutan uno a uno | Aprobada: máximo activo observado = 1 |
| Scheduler | Fallo aislado continúa y dependencia produce skipped | Aprobada |
| Scheduler | Reintento es por fuente y resume no repite éxitos | Aprobada |
| Publicación | Parcial/fallido no reemplaza el último publicado | Aprobada |
| Publicación | Proveedores válidos publican aunque otro falle | Aprobada: el orquestador publica el proveedor válido y conserva fallido el restante |
| Notificaciones | Publicación y fallo encolan eventos idempotentes por proveedor | Aprobada: `DATA_CHANGED` y `SCRAPE_FAILED`; reanudar no duplica el outbox |
| Consultas | Últimos planes, precios, matriz y estadísticas publicadas | Aprobada en servicios; endpoint ancho autenticado comprobado |
| Artefactos | Ruta relativa segura, hash y escritura atómica | Aprobada |
| Muestra | 27 planes, 367 fuentes, 402 reseñas y 27 filas anchas | Aprobada: además 1.674 valores tipados |
| Integración core | Fixture planes→limpieza→equivalencias→reseñas→publicación | Aprobada sin CLI ni shell |
| Comandos | Config import/export/validate/publish, seed y dry-run | Aprobada |
| Regresión | Ruff, suite offline, docs-check y diff-check | Aprobada: 253 pruebas, 4 excluidas, lint/checks/docs/builder/diff correctos |

La tabla se actualiza únicamente con resultados ejecutados. Los conteos de muestra son controles
de integración, no reglas permanentes.

