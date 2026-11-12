# Contratos de salida de la CLI

## Fuente autoritativa y reglas comunes

Se inspeccionaron, sin modificarlos, los tres XLSX de `ejemplos_data/output/`. Son diccionarios de
datos: especifican campos, orden, tipo y ejemplos, pero no contienen archivos CSV/JSON serializados.
Por ello se aplican las reglas fallback exigidas por el prompt:

- CSV delimitado por coma, UTF-8 sin BOM, encabezado en el orden siguiente;
- nulo como campo vacío y booleano como `TRUE`/`FALSE`;
- JSON como array raíz de objetos con las mismas claves;
- nulo como `null`, booleanos y números JSON reales;
- fechas ISO-8601; timestamps de ingesta UTC terminados en `Z`;
- comillas, comas, tildes y emojis se conservan con el quoting estándar CSV;
- los saltos internos se quoted si el adapter los entrega; Google Maps aplana sus separadores de
  línea visibles a espacios para mantener una reseña por línea física.

No se encontraron versiones incompatibles. Los IDs de esquema son explícitos y no se infieren en
tiempo de ejecución.

Estos contratos describen exclusivamente la salida raw de `scraper_cli`. `data_cleaning` puede
eliminar columnas completamente vacías y `data_transformation` puede agregar auxiliares o derivados
analíticos; esas reglas se documentan en [Limpieza](../data/DATA_CLEANING.md) y
[Transformación](../data/DATA_TRANSFORMATION.md). No constituyen una nueva versión del contrato del scraper
porque no modifican su archivo ni sus mappers.

## `plans_v2`

Referencia: `estructura de csv planes y precios.xlsx`.

| Orden | Campo | Tipo lógico / origen |
|---:|---|---|
| 1 | `timestamp_utc` | fecha-hora UTC de ingesta |
| 2 | `competidor_id` | `providers.code` del TOML |
| 3 | `competidor_nombre` | `providers.name` del TOML |
| 4 | `plan_id` | ID externo; si falta, hash determinista documentado |
| 5 | `plan_nombre` | texto público |
| 6 | `producto` | producto o familia a la que pertenece el plan; texto o nulo |
| 7 | `moneda` | código de moneda |
| 8 | `precio_mensual` | número o nulo |
| 9 | `precio_anual_total` | número o nulo |
| 10 | `precio_mensual_efectivo` | número o nulo |
| 11 | `descuento_anual_pct` | porcentaje numérico o nulo |
| 12 | `es_oferta_activa` | booleano o nulo |
| 13 | `promocion_texto` | texto o nulo |
| 14 | `url_fuente` | URL pública |

`plans_v2` añade `producto` respecto de `plans_v1`. El campo puede ser nulo para adapters antiguos o fuentes que no expongan esta clasificación; forma parte del ID derivado cuando falta un ID externo.
La periodicidad no forma parte por sí sola de `plan_id`: si una fuente publica el mismo plan en
variantes mensual y anual, el adapter debe emitir una fila con ambos precios. En Siigo se usa la
clave externa del producto; los antiguos IDs `clave:1` y `clave:12` son artefactos históricos y no
se emiten en ejecuciones nuevas.

El DTO conserva `discount_percentage` y `price_after_discount`. El mapper usa los precios explícitos
del DTO; para periodicidad mensual/anual puede usar el precio canónico. El precio efectivo usa
`price_after_discount` y, como último fallback anual, `precio_anual_total / 12`. No se inventa un
descuento ausente.

## `plan_features_v1`

Referencia: `estructura de csv caracteristicas de los planes.xlsx`.

1. `plan_id`
2. `competidor_id`
3. `categoria_modulo`
4. `nombre_modulo`
5. `incluido`
6. `costo_adicional`

`offered` se proyecta como verdadero, `not_offered` como falso y `unknown` como nulo. Categoría y
costo permanecen nulos cuando el scraper no los obtiene.

## `reviews_v1`

Referencia: `estructura csv reseñas_respuestas.xlsx`.

1. `review_id`
2. `competidor_id`
3. `app_id`
4. `plataforma`
5. `pais_codigo`
6. `fecha_comentario`
7. `usuario_nombre`
8. `calificacion_estrellas`
9. `comentario_cliente`
10. `version_app`
11. `likes_comentario`
12. `categoria_tema`
13. `sentimiento`
14. `tiene_respuesta`
15. `fecha_respuesta`
16. `respuesta_desarrollador`
17. `dias_para_responder`
18. `timestamp_ingesta`

`review_id` usa el ID externo dentro del namespace proveedor/fuente o un hash estable si falta.
`dias_para_responder` se deriva sólo cuando existen ambas fechas. `categoria_tema` y `sentimiento`
siempre son nulos: pertenecen a un enriquecimiento posterior. Un cero de likes y una respuesta
falsa se conservan; no se confunden con ausencia.

## Validación

Antes de publicar, cada fila debe tener exactamente las claves de su versión: faltantes y extras
son errores de salida (código 5). Los contratos se prueban con orden exacto, tipos, nulos y contenido
Unicode. Los XLSX originales no son modificados ni necesarios durante la ejecución.
