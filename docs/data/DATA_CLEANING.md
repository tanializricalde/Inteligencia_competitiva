# Limpieza de datos

## Propósito y límite

`data_cleaning` corrige representación y calidad sin crear interpretación analítica. Recibe los
CSV o arreglos JSON del scraper, no modifica el archivo raw y produce una capa limpia que entra
directamente en `data_transformation`. No calcula sentimiento, no aplana características y no
compara precios.

La API canónica es `clean_dataset()` y la CLI es `python -m data_cleaning`. No existen rutas de
procesamiento alternativas ni dependencias de Django, base de datos o red.

## Ausentes y columnas vacías

- Una cadena vacía o compuesta sólo por espacios se convierte en `pd.NA`.
- Textos legítimos como `no data`, `N/A`, `none`, `null` o `-` no se interpretan como centinelas.
- Tras estandarizar vacíos, toda columna completamente nula se elimina y aparece en
  `empty_columns_removed` y en el reporte.
- Una columna parcialmente nula se conserva. CSV serializa el nulo como campo vacío y JSON como
  `null`.
- Se retiran columnas de motivo de ausencia conocidas, como `comentario_estado`, `rating_only` o
  `extraction_error`; nunca se generan reemplazos equivalentes.

Por ello el esquema clean es deliberadamente dinámico. En las muestras actuales desaparecen, si
continúan totalmente vacías, `sentimiento`, `categoria_tema`, `fecha_respuesta`,
`dias_para_responder` y `costo_adicional`. Transformación puede crear un derivado calculable con
otro nombre, pero no restaura una columna vacía sin contenido.

## Texto e identificadores

En texto visible se eliminan espacios exteriores y caracteres de control. Tabulaciones y saltos de
línea se sustituyen por un separador simple; los espacios internos ordinarios, tildes, diéresis,
`ñ`, mayúsculas y puntuación se conservan. No se aplica una reescritura Unicode destructiva ni
`snake_case` al original.

Los identificadores (`review_id`, `plan_id`, `competidor_id`), URLs y códigos externos no se
recortan ni convierten a número. Así se conservan ceros iniciales, separadores y valores largos.
Las respuestas terminadas en `… Más` se conservan y generan `possibly-truncated-response`.

## Duplicados e integridad observable

Sólo se elimina un duplicado exacto. Filas que comparten la clave estable pero difieren en otros
valores se conservan y generan `duplicate-key-conflict`. En características se calcula internamente
una clave de comparación para reportar colisiones como `Consulta sobre módulos adicionales` frente a
una variante de puntuación; la clave no sustituye la etiqueta original.

La integridad entre características y planes requiere disponer de ambos conjuntos. La API tabular
por tipo no inventa un catálogo externo; `orphan_keys` queda disponible en el reporte para una
orquestación futura que reciba esa relación.

## Políticas numéricas

`data_pipeline.policies.NUMERIC_POLICIES` registra por perfil y campo la estrategia, justificación
y valor opcional. Las estrategias son `keep_na`, `zero`, `mean`, `median`, `fixed`, `reject` y
`drop_row`.

Las políticas predeterminadas son conservadoras:

| Perfil | Campos | Estrategia | Motivo |
| --- | --- | --- | --- |
| review | `calificacion_estrellas`, `likes_comentario`, `dias_para_responder` | `keep_na` | La ausencia no permite inferir calificación, votos ni plazo. |
| plan | precios y descuento | `keep_na` | No se imputan importes comerciales. |
| feature | `costo_adicional` | `keep_na` | Costo desconocido no significa cero. |

Una columna eliminada por estar vacía queda registrada con `column_present=false`. Media, mediana
y valor fijo reportan el valor usado y filas afectadas. `reject` y `drop_row` excluyen las filas;
`reject` además genera una incidencia y cuenta `rejected_rows`. Una columna numérica desconocida
se conserva sin imputar, genera `numeric-policy-missing` y falla con `strict=True`.

## API Python

```python
import pandas as pd
from data_cleaning import NumericPolicy, NumericStrategy, clean_dataset

frame = pd.read_csv("data/raw/plans.csv", dtype="string", keep_default_na=False)
result = clean_dataset(
    frame,
    "plan",
    numeric_policies={
        "precio_mensual": NumericPolicy(
            NumericStrategy.KEEP_NA,
            "El precio ausente no puede inferirse",
        )
    },
)
clean = result.data
print(result.empty_columns_removed, result.report.as_dict())
```

`CleaningResult` expone datos, tipo, incidencias, filas de entrada/salida/rechazadas, filas vacías
y duplicadas, celdas limpiadas, columnas vacías eliminadas, políticas aplicadas y
`QualityReport`. La operación es idempotente para sus reglas predeterminadas.

## CLI

```bash
.venv/bin/python -m data_cleaning data/raw/reviews.csv \
  --output data/clean/reviews.csv --report data/reports/reviews-clean.json
.venv/bin/python -m data_cleaning data/raw --output-dir data/clean --strict
```

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m data_cleaning .\data\raw\reviews.csv `
  --output .\data\clean\reviews.csv --report .\data\reports\reviews-clean.json
```

`--report` produce un arreglo JSON (un objeto por tipo consolidado) con versión de reglas,
conteos, nulos, políticas e incidencias. El reporte es auditoría: no agrega columnas al dataset.
`--csv-null-value TEXT` cambia únicamente cómo se representan los nulos al escribir CSV; no cambia
los datos internos ni los reportes JSON. No uses un marcador textual en un CSV intermedio que
después deba volver a leer el pipeline: usa el campo vacío predeterminado o JSON.
Las opciones de entradas múltiples, detección, formatos, sobrescritura y códigos se describen en
[Pipeline de datos](DATA_PIPELINE.md).

## Ejemplo

Entrada:

```json
[{"review_id":"0001:A","comentario_cliente":"  Muy\n bien  ","sentimiento":" "}]
```

Salida limpia:

```json
[{"review_id":"0001:A","comentario_cliente":"Muy bien"}]
```

El reporte incluye `sentimiento` en `empty_columns_removed`; no crea una columna que explique su
ausencia.
