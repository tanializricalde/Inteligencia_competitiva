# Pipeline de datos posterior al scraping

## Flujo y límites

El procesamiento manual tiene tres etapas independientes:

```text
scraper_cli -> archivo raw -> data_cleaning -> archivo clean
            -> data_transformation -> archivo normalized
```

- `scraper_cli` conserva lo observado y emite `plans_v2`, `plan_features_v1` o `reviews_v1`.
- `data_cleaning` corrige calidad, elimina columnas totalmente vacías y no interpreta el negocio.
- `data_transformation` convierte tipos y añade sólo auxiliares o derivaciones deterministas.

Ninguna de las dos etapas posteriores importa Django, usa base de datos, abre un navegador o hace
llamadas de red. Sus rutas son explícitas; `data/raw`, `data/clean` y `data/normalized` son una
convención recomendada, no un requisito.

## Contrato entre etapas

Se admiten CSV con coma y UTF-8 sin BOM, o JSON como arreglo raíz de objetos. En CSV el nulo es un
campo vacío; en JSON es `null`. Los identificadores se leen como texto desde CSV para conservar
ceros iniciales. Las filas mantienen su orden, salvo las filas vacías, rechazadas por una política
explícita y duplicados exactos que la limpieza elimina. Tras convertir vacíos a `pd.NA`, limpieza
elimina y reporta columnas completamente nulas; conserva columnas adicionales. Transformación
omite las adicionales con una incidencia, conserva en orden las columnas raw presentes y agrega
derivados analíticos aprobados. No se crean columnas con el motivo de ausencia.

Cada archivo de entrada siempre es de sólo lectura. Una salida existente exige `--overwrite`, pero
ni siquiera esa opción permite usar la misma ruta de una entrada. Los directorios padres de la
salida se crean cuando hacen falta y la publicación se realiza mediante un archivo temporal.

## Entradas múltiples y consolidación

El argumento `INPUT_PATH` puede repetirse y aceptar archivos o carpetas. Las carpetas se recorren
recursivamente en orden determinista; se consideran archivos `.csv` y `.json`, se ignoran otras
extensiones y no se siguen enlaces simbólicos. Si el mismo archivo aparece mediante una carpeta y
como ruta explícita, se procesa una sola vez.

Una carpeta o más de una ruta activa el modo lote:

1. se lee y detecta el tipo de cada archivo de forma independiente;
2. se agrupan las entradas compatibles como `review`, `plan` o `feature`;
3. se concatenan las filas de cada grupo y la etapa se ejecuta una vez sobre el conjunto;
4. se publica un único archivo por tipo.

La consolidación ocurre antes de limpiar o transformar. Por ello, la limpieza puede eliminar un
duplicado exacto aunque sus copias estén en archivos distintos. El proceso carga cada grupo
completo en memoria; no está diseñado todavía para conjuntos que necesiten procesamiento por
fragmentos.

## Detección automática

`data_pipeline.detect_dataset_type()` es la única implementación usada por ambas CLI. Combina:

1. palabras inequívocas en la ruta o nombre (`reviews`, `plans`, `features` y equivalentes en español);
2. firmas de columnas: `review_id` + `comentario_cliente`, `plan_id` + `plan_nombre`, o
   `plan_id` + `nombre_modulo`.

La firma `plan_features` se interpreta como características, no como dos tipos. Una contradicción
entre ruta y columnas, varias firmas simultáneas o ninguna señal produce código `2` para un archivo
individual. En modo lote, una entrada indeducible se omite, se informa y el proceso termina con
código `4`; `--strict` convierte esa advertencia en error y evita publicar las salidas.

Con un único archivo, `--type review|plan|feature` sigue siendo un override explícito compatible
con el comportamiento anterior. En modo lote, `--type` es un filtro seguro: cada archivo debe poder
deducirse como el tipo solicitado y los demás tipos se omiten. La CLI reutiliza las columnas del
archivo ya cargado, por lo que no hay una segunda lectura. La API de detección aislada lee sólo la
cabecera CSV; para JSON valida el arreglo pequeño completo y usa las claves del primer objeto.

## Opciones y códigos comunes

Ambos comandos aceptan uno o más `INPUT_PATH`, `--output`, `--output-dir`,
`--review-filename`, `--plan-filename`, `--feature-filename`,
`--type auto|review|plan|feature`, `--format csv|json`, `--overwrite`, `--strict` y
`--report REPORT_PATH`. `--csv-null-value TEXT` permite representar un nulo con texto sólo al
serializar salidas CSV; el default continúa siendo un campo vacío. Transformación admite además
`--wide-output OUTPUT_PATH` para publicar la vista ancha de un único grupo de características, y `--feature-rules`,
`--feature-rules-report` y `--strict-feature-rules` para equivalencias configurables.

- `--output` escribe un único tipo. En lote requiere `--type`.
- `--output-dir` escribe una salida por tipo detectado. Los nombres predeterminados son
  `reviews.csv`, `plans.csv` y `features.csv`.
- Las opciones `--*-filename` sustituyen sólo el nombre dentro de `--output-dir`; no admiten una
  ruta. Si omiten extensión se añade `.csv`, o la extensión indicada por `--format`.
- `--format` fija el formato de todas las salidas; si se omite, cada nombre `.csv`/`.json` lo
  determina y los nombres sin extensión usan CSV.
- `--csv-null-value` se aplica a salidas principales y a `--wide-output`, pero nunca modifica JSON
  ni reportes. No admite saltos de línea ni bytes nulos. Es una representación de salida, no un
  centinela reconocido automáticamente al volver a leer un CSV.
- `--strict` evita escribir cualquier salida ante una incidencia recuperable detectada durante la
  lectura, selección o procesamiento. Sin modo estricto se conservan resultados seguros y se
  reportan advertencias.
- `--report` escribe atómicamente un arreglo JSON por tipo con conteos, nulos, columnas eliminadas,
  políticas, colisiones, discrepancias e incidencias.
- `--wide-output` sólo corresponde a transformación de `feature`; limpieza lo rechaza antes de
  publicar. Una colisión normalizada produce nulo en la celda ancha y conserva las filas largas.
- `--feature-rules` cambia sólo la vista ancha de `feature`; sin esa opción se conserva el pivote
  dinámico histórico. Su reporte de cobertura es independiente de `--report`.

Antes de publicar se validan todos los destinos: no pueden coincidir entre sí ni con entradas y
ninguno puede existir sin `--overwrite`. Esto evita producir sólo una parte por errores de destino.

- `0`: archivo completo sin incidencias.
- `2`: tipo, detección o datos inválidos en modo estricto.
- `4`: archivo producido con advertencias.
- `5`: error esperado de lectura o escritura.

El resumen normal y las advertencias se escriben en stderr; los datos van únicamente al archivo.

## Pipeline completo en Linux

```bash
mkdir -p data/raw data/clean data/normalized
.venv/bin/python -m scraper_cli reviews --config config.example.toml --provider competidor_demo --output data/raw/reviews.csv
.venv/bin/python -m data_cleaning data/raw/reviews.csv --output data/clean/reviews.csv
.venv/bin/python -m data_transformation data/clean/reviews.csv --output data/normalized/reviews.csv --report data/reports/reviews.json
```

Consolidar una carpeta mixta y personalizar nombres:

```bash
.venv/bin/python -m data_cleaning data/raw --output-dir data/clean --review-filename opiniones.json --plan-filename catalogo.csv
.venv/bin/python -m data_transformation data/clean --output-dir data/normalized --format json
```

Consolidar sólo reseñas tomadas de varias rutas:

```bash
.venv/bin/python -m data_cleaning data/raw/enero data/raw/febrero/reviews.csv --type review --output data/clean/reviews.csv
```

### Flujo completo con `NULL` textual en los CSV finales

Usa JSON como formato intermedio para que el nulo continúe siendo `null` real. Escribir `NULL` en
el CSV limpio y volver a leerlo no es equivalente: el pipeline conserva deliberadamente esa
cadena como texto legítimo.

```bash
mkdir -p data/clean-null-flow data/normalized-null-flow data/reports-null-flow
.venv/bin/python -m data_cleaning data/raw/ \
  --output-dir data/clean-null-flow \
  --format json \
  --report data/reports-null-flow/clean-quality-report.json \
  --overwrite
.venv/bin/python -m data_transformation data/clean-null-flow/ \
  --output-dir data/normalized-null-flow \
  --format csv \
  --csv-null-value NULL \
  --wide-output data/normalized-null-flow/features-wide.csv \
  --feature-rules feature_rules/feature-equivalence.example.json \
  --feature-rules-report data/normalized-null-flow/feature-rules-report.json \
  --report data/normalized-null-flow/quality-report.json \
  --overwrite
```

## Pipeline completo en Windows PowerShell

```powershell
New-Item -ItemType Directory -Force .\data\raw, .\data\clean, .\data\normalized
.\.venv\Scripts\python.exe -m scraper_cli reviews --config .\config.example.toml --provider competidor_demo --output .\data\raw\reviews.csv
.\.venv\Scripts\python.exe -m data_cleaning .\data\raw\reviews.csv --output .\data\clean\reviews.csv
.\.venv\Scripts\python.exe -m data_transformation .\data\clean\reviews.csv --output .\data\normalized\reviews.csv
```

Consolidar una carpeta mixta y personalizar nombres:

```powershell
.\.venv\Scripts\python.exe -m data_cleaning .\data\raw --output-dir .\data\clean --review-filename opiniones.json --plan-filename catalogo.csv
.\.venv\Scripts\python.exe -m data_transformation .\data\clean --output-dir .\data\normalized --format json
```

Consolidar sólo reseñas tomadas de varias rutas:

```powershell
.\.venv\Scripts\python.exe -m data_cleaning .\data\raw\enero .\data\raw\febrero\reviews.csv --type review --output .\data\clean\reviews.csv
```

Flujo completo con `NULL` textual en los CSV finales y JSON como intermedio seguro:

```powershell
New-Item -ItemType Directory -Force .\data\clean-null-flow, .\data\normalized-null-flow, .\data\reports-null-flow
.\.venv\Scripts\python.exe -m data_cleaning .\data\raw `
  --output-dir .\data\clean-null-flow `
  --format json `
  --report .\data\reports-null-flow\clean-quality-report.json `
  --overwrite
.\.venv\Scripts\python.exe -m data_transformation .\data\clean-null-flow `
  --output-dir .\data\normalized-null-flow `
  --format csv `
  --csv-null-value NULL `
  --wide-output .\data\normalized-null-flow\features-wide.csv `
  --feature-rules .\feature_rules\feature-equivalence.example.json `
  --feature-rules-report .\data\normalized-null-flow\feature-rules-report.json `
  --report .\data\normalized-null-flow\quality-report.json `
  --overwrite
```

Para planes, ejecuta primero `scraper_cli plans`; procesa por separado el archivo de planes con
`--type plan` y el de características con `--type feature` si sus nombres no permiten inferirlos.

## Problemas habituales

- **Tipo ambiguo o contradictorio:** revisa que no hayas dado a un archivo de planes un nombre de
  reseñas; si es intencional, usa `--type`.
- **Columnas desconocidas:** contrasta la entrada con [Contratos CLI](../cli/CLI_OUTPUT_SCHEMAS.md). La
  limpieza puede conservarlas; la transformación las omite con advertencia.
- **Código 4:** la salida existe y conserva todos los datos seguros, pero debes revisar las
  advertencias antes de usarla para análisis.
- **Código 5:** comprueba extensión, permisos, ruta y `--overwrite`.
- **No se encontraron entradas deducibles:** revisa firmas/nombres; con `--type` el archivo debe
  poder detectarse como ese tipo en modo lote, no basta con forzar la etiqueta.
- **La carpeta de salida está dentro de la entrada:** separa `raw`, `clean` y `normalized`. Si un
  destino coincide con una entrada la ejecución se rechaza; otros artefactos antiguos dentro del
  árbol sí se considerarían entradas.
- **Fechas sin zona:** no se supone una zona horaria; quedan nulas y se reportan.
- **Reglas de características:** valida primero el JSON y revisa capturas, colisiones, reglas no
  usadas y fallback según [Reglas de equivalencia](FEATURE_EQUIVALENCE_RULES.md).

## Limitaciones conocidas

No hay traducción, sentimiento lingüístico, enriquecimiento, conversión de moneda ni inferencia de
fechas relativas. `sentimiento_por_calificacion` es sólo una clasificación determinista de estrellas.
Los decimales aceptan punto o coma mediante reglas documentadas, pero una representación ambigua
queda nula y se reporta. Los archivos se cargan completos con pandas; no hay paralelismo ni
procesamiento por fragmentos.
