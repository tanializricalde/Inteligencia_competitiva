# Reglas de equivalencia de características

## Propósito y archivos

La vista ancha tradicional crea una columna por cada `nombre_modulo_normalizado`. Esto conserva
todo lo observado, pero descripciones equivalentes como `Usuarios: 2`, `6 Usuarios` o
`2 usuarios | 1 usuario contador` terminan en columnas distintas. Las reglas de equivalencia son
una opción de `data_transformation` que convierte esas descripciones en columnas canónicas sin
alterar la tabla larga ni los scrapers.

El repositorio entrega:

- [`feature-equivalence.example.json`](../../feature_rules/feature-equivalence.example.json):
  configuración v1 ejecutable para Anfibius, iDrix, Perseo y Siigo;
- [`feature-equivalence.schema.json`](../../feature_rules/feature-equivalence.schema.json): JSON
  Schema draft 2020-12 para autocompletado y validación en editores;
- `data_transformation.feature_rules`: cargador, validación, motor y reporte puros.

La función es opt-in. Sin `--feature-rules`, `TransformationResult.wide_data` y `--wide-output`
continúan usando exactamente el pivote dinámico histórico. Con reglas, la tabla larga normalizada
también permanece igual; sólo cambia la vista ancha derivada.

Con reglas, el motor produce además una tabla larga tipada `feature_values`; la vista ancha se
deriva de esa tabla. La CLI la publica mediante `--feature-values-output` junto con `--run-id` y
Django la usa para persistir características sin crear columnas físicas dinámicas.

## Primera ejecución

Linux:

```bash
.venv/bin/python -m data_transformation data/clean/features.csv \
  --type feature \
  --output data/normalized/features.csv \
  --wide-output data/normalized/features-equivalentes.csv \
  --feature-rules feature_rules/feature-equivalence.example.json \
  --feature-rules-report data/reports/feature-equivalence.json \
  --overwrite
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m data_transformation .\data\clean\features.csv `
  --type feature `
  --output .\data\normalized\features.csv `
  --wide-output .\data\normalized\features-equivalentes.csv `
  --feature-rules .\feature_rules\feature-equivalence.example.json `
  --feature-rules-report .\data\reports\feature-equivalence.json `
  --overwrite
```

`--strict-feature-rules` convierte capturas inválidas y competidores desconocidos recuperables en
errores. Conflictos configurados como `error`, configuración inválida y colisiones de columnas son
fatales siempre y se detectan antes de publicar salidas. `--overwrite` sigue siendo obligatorio
para reemplazar cualquier salida o reporte existente.

## Ejemplo mínimo de entrada y salida

Entrada larga:

```csv
plan_id,competidor_id,nombre_modulo,incluido
siigo_plan,siigo_ec,2 usuarios | 1 usuario contador,1
perseo_plan,perseo,Usuarios: 3,1
perseo_plan,perseo,No configurado,1
```

Fragmento conceptual de la vista ancha:

```csv
competidor_id,plan_id,usuarios_normales,usuarios_contador,usuarios_sin_clasificar,usuarios_totales,no_configurado
siigo_ec,siigo_plan,2,1,,3,0
perseo,perseo_plan,0,0,3,3,1
```

Los campos vacíos son nulos reales. La salida CSV nunca escribe `pd.NA`; JSON usa `null`. Un cero
configurado y `false` son hechos distintos de ausencia.

En la configuración ejemplo vigente, las cinco columnas numéricas base usan `default: 0`, por lo
que usuarios no observados y capacidad de nómina no informada se representan con cero en la vista
ancha. Esta es una decisión explícita de reporte solicitada para este ejemplo; la tabla larga
continúa conservando el hecho original. Otras configuraciones pueden usar `null` si necesitan
distinguir ausencia de evidencia.

## Estructura v1

La raíz admite sólo estas secciones:

| Sección | Responsabilidad |
| --- | --- |
| `schema_version` | Versión exacta del contrato; actualmente sólo `1`. |
| `input` | Claves, texto, booleano de inclusión y deduplicación. |
| `behavior` | Competidores desconocidos, conflictos, capturas y fallback. |
| `columns` | Columnas canónicas, tipos, defaults, reductores, tags y etiquetas. |
| `derived_columns` | Cálculos cerrados ejecutados después de reducir aportes. |
| `rule_sets` | Reglas comunes o específicas reutilizables. |
| `competitors` | Rule sets y defaults seleccionados por `competidor_id`. |

El cargador rechaza claves desconocidas, nombres que no sean `snake_case`, referencias ausentes,
tipos incompatibles, IDs repetidos, regex inválidas, capturas inexistentes, dependencias cíclicas y
colisiones con las claves de agrupación. La validación de runtime es propia y no necesita instalar
`jsonschema`; el schema es una ayuda adicional para editores.

### Entrada y deduplicación

`group_by` define una fila de salida, normalmente `competidor_id` y `plan_id`.
`normalized_text_field` se calcula con la normalización canónica si aún no existe. `incluido` se
convierte a booleano anulable. Después se eliminan duplicados exactos por `deduplicate_by`, antes de
usar reductores como `sum`, para no contar dos veces la misma observación.

Toda columna listada en `deduplicate_by` debe existir o poder calcularse. Las claves de agrupación
no admiten nulos.

### Columnas y tipos

Los tipos cerrados son `boolean`, `integer`, `decimal`, `string` y `string_list`. Cada columna
canónica declara `default` y `reducer`. `null` JSON representa desconocido; no uses las cadenas
`"NULL"`, `"None"` o `"pd.NA"`.

Reductores permitidos:

| Reductor | Tipos | Resultado |
| --- | --- | --- |
| `sum`, `max`, `min` | integer, decimal | Combina aportes numéricos no nulos. |
| `first`, `last` | cualquiera | Primer o último aporte no nulo en orden estable. |
| `any`, `all` | boolean | Disyunción o conjunción de aportes presentes. |
| `join_unique` | string, string_list | Valores únicos conservando el orden. |
| `error` | cualquiera | Acepta repeticiones iguales y falla ante valores distintos. |

En CSV un `string_list` se separa con `|`; en JSON se conserva como arreglo.

### Reglas, prioridad y consumo

`when.operator` sólo admite `equals` o `regex`. Una regex puede usar `IGNORECASE` y `MULTILINE`;
se compila durante la carga. Para extraer datos usa grupos con nombre:

```json
{
  "id": "usuarios_y_contador",
  "priority": 200,
  "when": {
    "field": "nombre_modulo",
    "operator": "regex",
    "pattern": "^(?P<normales>\\d+) usuarios? \\| (?P<contador>\\d+) usuarios? contador(?:es)?$",
    "flags": ["IGNORECASE"]
  },
  "outputs": [
    {"column": "usuarios_normales", "value": {"capture": "normales"}},
    {"column": "usuarios_contador", "value": {"capture": "contador"}}
  ],
  "consume": true
}
```

Cada output tiene exactamente una fuente: `capture`, `literal` o `field`. Las reglas se ordenan por
prioridad descendente y orden de declaración. Una regla `consume: true` evita reglas posteriores y
el fallback. Con `multiple_matching_rules: error`, dos reglas consumidoras compatibles generan un
conflicto explícito; `first` conserva la primera según el orden estable.

### Derivados

Los derivados se calculan después de todas las reglas y reductores. Sólo existen:

- `sum_columns`: suma componentes presentes; `null_if_all_null` conserva desconocido cuando todos
  son nulos y respeta un cero explícito;
- `count_true`: cuenta columnas booleanas seleccionadas por `tag`;
- `join_labels`: concatena sus `label` siguiendo el orden de declaración de `columns`.

Por eso `usuarios_totales` puede sumar usuarios normales, contador, sin clasificar y móviles, pero
nunca `nomina_personas_max`. `Nómina (5 personas)` significa capacidad de nómina: establece
`nomina_incluida` y `nomina_personas_max`, no cinco usuarios del sistema.

### Características no configuradas

`behavior.unmatched.mode` controla filas que ninguna regla consume:

- `dynamic_boolean` mantiene la compatibilidad: crea una columna normalizada, usa `incluido` y el
  reductor/default configurados;
- `ignore` las registra pero no crea columna;
- `error` detiene la ejecución.

Una columna dinámica que colisione con una clave, columna canónica o derivada siempre falla. En el
modo recomendado, una característica no observada usa `default: false`; esto es una decisión de la
vista configurada y no modifica la tabla larga.

## Reglas incluidas

La configuración ejemplo incorpora:

- comunes: nómina con límite, `Nómina de N personas*` y nómina sin cantidad;
- Siigo: usuarios más contador en una descripción y filas adicionales de contador;
- iDrix: `Usuarios: N` y `Usuarios contador: N`;
- Perseo: `N Usuarios`, usuarios más aplicación móvil y `Licencia(s) App PerseoMóvil`;
- módulos compartidos o variantes inequívocas: facturación, inventario, contabilidad, bancos,
  conciliación, activos fijos, importaciones, tesorería, BI, reportes, capacitación, soporte,
  producción, bodegas, liquidación de tarjetas, compras y cartera;
- capacidades útiles de un proveedor que tenían varias redacciones: aplicación móvil, facturación
  en lote, catálogo, API, punto de venta y módulos adicionales por consultar.

La [auditoría analítica](FEATURE_EQUIVALENCE_ANALYSIS.md) documenta la matriz completa por
competidor, los nombres originales que alimentan cada columna y las claves que deliberadamente
continúan dinámicas por falta de evidencia suficiente.

Los defaults de Perseo fijan usuarios normales/contador en cero porque el ejemplo de negocio lo
declara explícitamente. En otros competidores permanecen nulos si no hubo aporte.

## Reporte de cobertura

`--feature-rules-report` escribe un objeto JSON separado con:

- reglas cargadas, utilizadas, conteos y reglas sin coincidencias;
- filas consumidas y procesadas por fallback;
- características no configuradas ordenadas por frecuencia;
- capturas inválidas y múltiples coincidencias;
- duplicados exactos eliminados y colisiones;
- competidores desconocidos;
- columnas canónicas y dinámicas generadas.

El motor no imprime. La CLI muestra sólo un resumen y devuelve código `4` cuando conserva una
salida con diagnósticos recuperables; configuración o conflictos fatales devuelven código `2` sin
escribir parcialmente.

## Extender y probar

Para agregar un competidor:

1. crea o reutiliza un `rule_set`;
2. añade su `competidor_id` exacto en `competitors`;
3. usa `column_defaults` sólo cuando ausencia signifique realmente cero/falso;
4. prueba variantes singular/plural y revisa el reporte de reglas no usadas.

Para agregar una columna canónica:

1. declárala una sola vez en `columns` con tipo/default/reductor;
2. referencia esa columna desde outputs;
3. si es módulo, añade `tags: ["module"]` y `label` para los derivados;
4. evita nombres reservados o que puedan producirse por fallback.

Prueba primero sobre una copia y no sobre `data/clean/features.csv`:

```bash
cp data/clean/features.csv /tmp/features-prueba.csv
.venv/bin/python -m data_transformation /tmp/features-prueba.csv \
  --type feature --output /tmp/features-normalizadas.csv \
  --wide-output /tmp/features-equivalentes.csv \
  --feature-rules feature_rules/feature-equivalence.example.json \
  --feature-rules-report /tmp/feature-report.json
```

PowerShell:

```powershell
Copy-Item .\data\clean\features.csv $env:TEMP\features-prueba.csv
.\.venv\Scripts\python.exe -m data_transformation $env:TEMP\features-prueba.csv `
  --type feature --output $env:TEMP\features-normalizadas.csv `
  --wide-output $env:TEMP\features-equivalentes.csv `
  --feature-rules .\feature_rules\feature-equivalence.example.json `
  --feature-rules-report $env:TEMP\feature-report.json
```

Compara filas/planes, revisa `unused_rules`, `unmatched_features`, `invalid_captures` y
`multiple_matches`. Ejecutar dos veces la misma entrada/configuración produce igual orden y datos.

## Evolución y limitaciones

Una extensión incompatible exige aumentar `schema_version`, publicar un schema nuevo y documentar
la migración; el cargador v1 no intenta adivinar versiones futuras. No hay fuzzy matching,
`contains`, plantillas, `eval`, código cargable ni reglas externas. Todo el archivo se procesa en
memoria y secuencialmente. Los patrones y defaults del ejemplo son una base técnica: nuevas
equivalencias comerciales deben confirmarse con el responsable de datos antes de declararlas.
