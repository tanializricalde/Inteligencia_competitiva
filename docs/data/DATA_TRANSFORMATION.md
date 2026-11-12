# Normalización y transformación de datos

## Propósito y contrato

`data_transformation` convierte datos limpios a vistas analíticas trazables. Conserva los campos
observados que permanezcan en la capa clean, convierte tipos cuando la regla es inequívoca y crea
columnas auxiliares o derivadas sin sustituir el hecho original. La API es `transform_dataset()` y
la CLI es `python -m data_transformation`.

Los esquemas `plans_v2`, `plan_features_v1` y `reviews_v1` siguen siendo los contratos raw del
scraper. La salida analítica conserva sus columnas presentes en orden y puede añadir derivados. Una
columna opcional eliminada por limpieza no se recrea como nula salvo que exista una regla de
cálculo, como `dias_para_responder`.

## Conversiones comunes

- Identificadores y texto permanecen como strings anulables; no pierden ceros ni separadores.
- Enteros usan `Int64`; estrellas válidas están entre 1 y 5 y likes son no negativos.
- Decimales usan `Float64`, aceptan punto/coma no ambiguos, deben ser no negativos y el porcentaje
  queda entre 0 y 100.
- Booleanos reconocen `true/false`, `yes/no`, `si/sí`, `1/0` sin distinguir mayúsculas y salen como
  `Int8`: `0`, `1` o `pd.NA`.
- Fechas ISO-8601 con zona se convierten a UTC y sufijo `Z`. Una hora sin zona no recibe UTC
  supuesto: queda nula y se reporta.
- Un valor inválido queda `pd.NA`, genera `invalid-value` con fila/columna y falla en modo estricto.

Las categorías controladas se expresan en auxiliares `snake_case`; el texto libre original nunca
se normaliza en el mismo campo.

## Reseñas

- `sentimiento_por_calificacion`: 1–2 `negative`, 3 `neutral`, 4–5 `positive`; ausente o inválida,
  `pd.NA`. No es análisis lingüístico.
- `plataforma_codigo` y, cuando existe, `categoria_tema_codigo` son claves auxiliares normalizadas.
- Una respuesta observada fuerza `tiene_respuesta=1`; una contradicción se reporta. Sin texto ni
  fecha de respuesta, un indicador desconocido se deriva como `0`.
- `dias_para_responder` sólo se calcula con ambas fechas válidas. No se usa cero para fechas
  desconocidas y una respuesta anterior se reporta.

## Planes y precios

`plan_nombre_normalizado` y `moneda_codigo` son auxiliares; `plan_nombre` y los importes informados
se conservan. Si existe `precio_anual_total`, se crean:

```text
precio_mensual_calculado = precio_anual_total / 12
diferencia_mensual = precio_mensual_informado - precio_mensual_calculado
diferencia_mensual_porcentaje = diferencia_mensual / precio_mensual_informado * 100
precio_inconsistente_bandera = abs(diferencia_mensual) > 0.01
```

Para comparar, `precio_mensual_efectivo` tiene precedencia cuando está informado; en otro caso se
usa `precio_mensual`. Ninguno se rellena ni reemplaza con el cálculo anual. Una diferencia es una
señal comercial, no una corrección automática, y se cuenta en el reporte.

## Características: largo y ancho

`TransformationResult.data` conserva la tabla larga canónica y añade
`nombre_modulo_normalizado`. `TransformationResult.wide_data` contiene una fila por
`competidor_id`/`plan_id` y una columna por clave normalizada, con `incluido` como `0`, `1` o nulo.
Cuando se usan reglas, `TransformationResult.feature_values` contiene primero el contrato largo
tipado y `wide_data` se reconstruye exclusivamente desde él; no existen dos rutas de cálculo.

Antes del pivote se detectan etiquetas o valores distintos que convergen en la misma clave. Las
filas largas se conservan y la celda conflictiva queda nula en la vista ancha. Una característica no
observada también queda nula; nunca se supone `false` por ausencia.

De forma opt-in, `feature_rules=` en la API o `--feature-rules` en la CLI sustituye únicamente ese
pivote por el motor versionado de equivalencias. Las reglas pueden extraer varios valores, reducir
aportes, calcular derivados y conservar características no consumidas como columnas dinámicas. La
tabla larga no cambia. Consulta [Reglas de equivalencia](FEATURE_EQUIVALENCE_RULES.md).

## API Python

```python
import pandas as pd
from data_transformation import transform_dataset

frame = pd.read_csv("data/clean/features.csv", dtype="string", keep_default_na=False)
result = transform_dataset(frame, "feature", strict=False)
long_view = result.data
wide_view = result.wide_data
print(result.report.as_dict())
```

Con reglas:

```python
from data_transformation import load_feature_rules, transform_dataset

rules = load_feature_rules("feature_rules/feature-equivalence.example.json")
result = transform_dataset(frame, "feature", feature_rules=rules)
wide_view = result.wide_data
coverage = result.feature_rules_report.as_dict()
```

`TransformationResult` expone datos, tipo, incidencias, filas, conversiones inválidas, valores
derivados, vista ancha opcional y reporte. Volver a transformar una salida analítica vuelve a
calcular los mismos derivados sin crear variantes paralelas.

## CLI

```bash
.venv/bin/python -m data_transformation data/clean/reviews.csv \
  --output data/normalized/reviews.csv --report data/reports/reviews.json
.venv/bin/python -m data_transformation data/clean/features.csv \
  --output data/normalized/features.csv \
  --feature-values-output data/normalized/feature-values.csv \
  --wide-output data/normalized/features-wide.csv \
  --feature-rules feature_rules/feature-equivalence.example.json \
  --run-id RUN_UUID \
  --feature-rules-report data/reports/feature-equivalence.json \
  --report data/reports/features.json
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m data_transformation .\data\clean\features.csv `
  --output .\data\normalized\features.csv `
  --feature-values-output .\data\normalized\feature-values.csv `
  --wide-output .\data\normalized\features-wide.csv `
  --feature-rules .\feature_rules\feature-equivalence.example.json `
  --run-id RUN_UUID `
  --feature-rules-report .\data\reports\feature-equivalence.json
```

`--wide-output` requiere que la ejecución incluya exactamente un grupo `feature`; no está
disponible en limpieza. `--report` escribe el reporte JSON común. Ambas rutas respetan
`--overwrite` y no pueden coincidir con una entrada o salida principal.
`--csv-null-value TEXT` representa los nulos de las salidas CSV principal y ancha con el texto
indicado; por ejemplo, `--csv-null-value NULL`. JSON y reportes siempre usan `null` JSON.
`--feature-rules-report` y `--strict-feature-rules` requieren `--feature-rules`. El reporte general
de calidad y el de cobertura de equivalencias son artefactos distintos.

### Contrato `feature-values`

`--feature-values-output` requiere `--feature-rules` y `--run-id`. Cada fila representa una sola
característica de un plan y tiene 14 columnas:

```text
run_id,plan_id,competidor_id,feature_code,value_type,value_boolean,value_integer,
value_decimal,value_text,value_json,availability,origin,rule_id,is_derived
```

Sólo una columna `value_*` puede contener valor. `value_type` es `boolean`, `integer`, `decimal`,
`string` o `string_list`; una lista usa JSON en `value_json`. `availability` distingue `present`,
`excluded`, `unknown` y `not_applicable`. `origin` distingue `rule`, `fallback`, `derived` y
`default`. Un default numérico cero conserva `availability=unknown`, de modo que no se confunde
con un cero observado. `rule_id` identifica la regla consumidora y `is_derived` marca cálculos.

## Limitaciones

No hay traducción, conversión de moneda, inferencia de fechas relativas, sentimiento por modelo ni
persistencia. Sin reglas, la vista ancha usa `incluido`; con reglas, sus límites dependen del schema
v1 documentado. `costo_adicional` permanece en la tabla larga. La validación referencial cruzada
entre archivos requiere una orquestación que proporcione a la vez planes y características.
