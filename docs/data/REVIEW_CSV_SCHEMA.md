# Esquema de exportación de reseñas

La versión canónica actual contiene exactamente 18 columnas UTF-8 en este orden. Cambiarlo requiere una versión nueva del esquema.

| # | Columna | Origen y regla |
| ---: | --- | --- |
| 1 | `review_id` | ID externo namespaced o fallback `hash-v1` determinista. |
| 2 | `competidor_id` | Siempre `ReviewSource.provider.code`; nunca `adapter_key`. |
| 3 | `app_id` | ID de aplicación; vacío cuando no aplica/desconocido. |
| 4 | `plataforma` | Etiqueta de la plataforma controlada. |
| 5 | `pais_codigo` | ISO-2 mayúsculo observado o de la fuente. |
| 6 | `fecha_comentario` | UTC ISO-8601 o vacío. |
| 7 | `usuario_nombre` | Nombre público o vacío. |
| 8 | `calificacion_estrellas` | Entero 1–5 o vacío. |
| 9 | `comentario_cliente` | Texto completo; puede ser vacío si la plataforma lo permite. |
| 10 | `version_app` | Versión reportada o vacío. |
| 11 | `likes_comentario` | Entero no negativo; vacío significa desconocido y `0` significa cero conocido. |
| 12 | `categoria_tema` | Vacío hasta un enriquecimiento completado. |
| 13 | `sentimiento` | Vacío hasta un enriquecimiento completado. |
| 14 | `tiene_respuesta` | `TRUE`, `FALSE` o vacío si la fuente no pudo determinarlo. |
| 15 | `fecha_respuesta` | UTC ISO-8601 o vacío. |
| 16 | `respuesta_desarrollador` | Texto público o vacío. |
| 17 | `dias_para_responder` | Diferencia de segundos/86400, redondeada a dos decimales; vacío si falta una fecha. |
| 18 | `timestamp_ingesta` | UTC ISO-8601 de la observación. |

## Formato

- Se usa `csv.DictWriter`; comas, comillas y saltos internos quedan correctamente quoted. El adapter
  de Google Maps sustituye los separadores de línea visibles por espacios antes de construir el DTO,
  de modo que sus exportaciones conservan una reseña por línea física.
- Los nulos son campos vacíos, nunca la cadena `NULL`.
- Las fechas usan sufijo `Z`; el almacenamiento interno es timezone-aware.
- El decimal usa punto.
- La exportación JSON contiene las mismas 18 claves en el mismo orden lógico y conserva nulos JSON.

## Filtros

La UI y los endpoints `.csv`/`.json` aceptan competidor, plataforma, país, estrellas, rango de fecha, respuesta, sentimiento, categoría, estado de enriquecimiento y búsqueda textual. La autorización `reviews.export_reviews` se verifica en servidor.

## Identidad y deduplicación

Si la plataforma ofrece ID, `review_id` lo incluye en un namespace por plataforma/fuente. Si falta, se calcula SHA-256 versionado con fuente/entidad, fecha, autor, rating y texto; no se usa sólo el comentario. Cambios en likes, respuesta u otros hechos significativos producen otra observación, no otra identidad.

El fallback puede colisionar si una plataforma oculta todos los campos estables o si el mismo autor publica contenido idéntico en el mismo instante. Un adapter debe preferir siempre el ID oficial permitido y conservar pruebas de esa estabilidad.
