# Referencia de uso de la CLI

La CLI ejecuta los adapters de planes y reseñas sin Django ni base de datos y exporta los
contratos canónicos en CSV o JSON. Esta guía documenta la interfaz de comandos; la estructura del
TOML está en [Configuración de la CLI](CLI_CONFIG.md) y las columnas de salida en
[Contratos de salida](CLI_OUTPUT_SCHEMAS.md).
Los ejemplos multilínea usan Bash/Linux; sus equivalentes PowerShell, rutas con `\` y binarios
`.\.venv\Scripts\python.exe` están en [Linux y Windows](../development/WINDOWS_LINUX.md).

## Formas de invocación

Desde el repositorio, con el entorno virtual activo:

```bash
python -m scraper_cli SUBCOMANDO [OPCIONES]
```

Desde la distribución independiente también puede usarse:

```bash
python run.py SUBCOMANDO [OPCIONES]
```

Las opciones pertenecen al subcomando y deben escribirse después de éste. Consulta la ayuda raíz o
la específica de un subcomando:

```bash
python -m scraper_cli --help
python -m scraper_cli plans --help
python -m scraper_cli reviews --help
python -m scraper_cli all --help
```

## Subcomandos

| Subcomando | Propósito | Requiere configuración | Genera archivos |
| --- | --- | --- | --- |
| `list-adapters` | Lista las claves de adapters registradas para planes y reseñas. | no | no |
| `validate-config` | Valida el TOML, sus tipos, claves y adapters sin ejecutar fuentes. | sí | no |
| `plans` | Ejecuta fuentes de planes y exporta planes y características. | sí | uno o dos |
| `reviews` | Ejecuta y pagina fuentes de reseñas. | sí | uno |
| `all` | Ejecuta primero planes y después reseñas. | sí | tres |

La ejecución es secuencial. Una fuente deshabilitada con `enabled = false` no se ejecuta ni puede
seleccionarse explícitamente con `--source`.

## Opciones comunes de ejecución

Estas opciones existen en `plans`, `reviews` y `all`:

| Opción | Valor | Comportamiento |
| --- | --- | --- |
| `--config PATH` | ruta | Obligatoria. Archivo TOML que define defaults, proveedores y fuentes. |
| `--provider CODE` | código | Filtra por `providers.code`. Puede repetirse para formar una selección. |
| `--source NAME` | texto exacto | Filtra por el `name` exacto de una fuente activa. Puede repetirse. |
| `--format csv\|json` | formato | Formato de los archivos; el predeterminado es `csv`. La extensión de la ruta no decide el formato. |
| `--limit N` | entero positivo | Máximo de registros por cada fuente; sustituye `[defaults].max_items`. |
| `--timeout SECONDS` | entero positivo | Sustituye el timeout TOML para cada solicitud o navegación. |
| `--pretty` | bandera | Indenta JSON. No cambia CSV. |
| `--verbose` | bandera | Añade contadores disponibles al resumen de `stderr`. |
| `--fail-fast` | bandera | Detiene nuevas fuentes después del primer fallo. En `all`, un fallo de planes evita ejecutar reseñas. |
| `--overwrite` | bandera | Permite reemplazar archivos existentes; sin ella la CLI termina con código `5`. |

Sin `--provider` se consideran todos los proveedores. Sin `--source` se consideran todas sus
fuentes activas del tipo solicitado. Los filtros repetidos se combinan como una selección, no como
una intersección:

```bash
python -m scraper_cli plans \
  --config config.toml \
  --provider anfibius \
  --provider perseo \
  --output planes.csv
```

`--source` compara el nombre visible completo, respeta mayúsculas y espacios, y no usa
`adapter_key`. En `all` el filtro se aplica independientemente a planes y reseñas; normalmente es
preferible usar `--provider` o ejecutar `plans` y `reviews` por separado cuando se necesita filtrar
una sola fuente.

## `list-adapters`

Muestra las claves válidas para `adapter_key` agrupadas por tipo:

```bash
python -m scraper_cli list-adapters
```

No lee `config.toml` ni accede a la red. Sirve para comprobar si una distribución contiene el
adapter esperado antes de configurar una fuente.

## `validate-config`

```text
python -m scraper_cli validate-config --config PATH
```

Ejemplo:

```bash
python -m scraper_cli validate-config --config config.toml
```

Valida todo el documento, incluso fuentes deshabilitadas. Detecta campos desconocidos, tipos o
rangos inválidos, códigos duplicados, URLs no admitidas y `adapter_key` inexistentes. No abre el
navegador, no ejecuta HTTP y no crea exportaciones.

## `plans`

```text
python -m scraper_cli plans [OPCIONES COMUNES] [--output PATH|-] [--features-output PATH]
```

Opciones propias:

| Opción | Comportamiento |
| --- | --- |
| `--output PATH` | Archivo principal; prevalece sobre el destino TOML. |
| `--output -` | Envía el contrato de planes a `stdout`. |
| `--features-output PATH` | Ruta del contrato de características. |

Si `--output` se omite, debe seleccionarse exactamente un proveedor y se usa
`[output].directory + providers.plans_filename`. Si `--features-output` se omite y la salida es un archivo, se deriva automáticamente. Por ejemplo,
`planes.csv` produce `planes_features.csv`, y `salida/planes.json` produce
`salida/planes_features.json`. El archivo se genera aunque no existan características y contendrá
al menos su encabezado CSV o un array JSON vacío.

Cuando `--output -` encuentra características, `--features-output` es obligatorio para impedir que
dos contratos diferentes se mezclen en `stdout`.

```bash
# CSV de todas las fuentes de planes activas
python -m scraper_cli plans \
  --config config.toml \
  --output ejemplos_data/planes.csv

# Una fuente concreta y reemplazo explícito
python -m scraper_cli plans \
  --config config.toml \
  --provider siigo_ec \
  --source "Planes públicos Siigo" \
  --limit 50 \
  --overwrite \
  --output ejemplos_data/planes-siigo.csv \
  --features-output ejemplos_data/caracteristicas-siigo.csv

# Planes JSON por stdout y características en un archivo separado
python -m scraper_cli plans \
  --config config.toml \
  --provider competidor_demo \
  --format json \
  --pretty \
  --output - \
  --features-output caracteristicas.json
```

## `reviews`

```text
python -m scraper_cli reviews [OPCIONES COMUNES] [--country ISO2] [--output PATH|-]
```

Sin `--output`, debe seleccionarse exactamente un proveedor y se usa
`[output].directory + providers.reviews_filename`.

`--country ISO2` sólo acepta un código de dos letras y tiene esta precedencia:

```text
--country → review_source.country_code → defaults.country_code → vacío
```

Ejemplos:

```bash
# Veinte reseñas de Anfibius
python -m scraper_cli reviews \
  --config config.toml \
  --provider anfibius \
  --limit 20 \
  --output ejemplos_data/resenas-anfibius.csv

# JSON indentado por stdout; el resumen permanece en stderr
python -m scraper_cli reviews \
  --config config.toml \
  --provider competidor_demo \
  --country PE \
  --format json \
  --pretty \
  --output -

# Backfill grande y acotado
python -m scraper_cli reviews \
  --config config.toml \
  --provider siigo_ec \
  --limit 500 \
  --timeout 120 \
  --overwrite \
  --output ejemplos_data/resenas-siigo.csv
```

En fuentes paginadas, `--limit` es por fuente. La cantidad efectiva también está restringida por
`max_pages`, el tamaño de página del adapter y los datos que el sitio publique. Google Maps añade
límites de desplazamientos, estabilidad, reintentos y `max_load_seconds`; puede tardar en un
backfill grande, pero no espera indefinidamente. Si falla antes de cargar la primera tarjeta no
genera una salida aparentemente válida; si se detiene después, exporta lo ya obtenido, muestra
`ADVERTENCIA` y termina con código `4` para identificar el archivo como parcial.

Una detención intermedia puede recuperarse en el lote siguiente. Si al terminar se alcanzó el
`--limit` solicitado o el total publicado, la advertencia parcial transitoria se elimina y el código
final es `0`; si todavía faltan registros, permanece la advertencia y el código `4`.

## `all`

```text
python -m scraper_cli all [OPCIONES COMUNES] [--country ISO2] [--output-dir DIR]
```

Si se omite `--output-dir`, se usa `[output].directory`.

Crea el directorio si no existe y escribe exactamente:

```text
DIR/
├── plans.csv
├── plan_features.csv
└── reviews.csv
```

Con `--format json`, las extensiones cambian a `.json`. `--country` sólo afecta reseñas. El comando
ejecuta planes antes que reseñas; con `--fail-fast`, cualquier fallo de planes omite toda la fase de
reseñas.

```bash
python -m scraper_cli all \
  --config config.toml \
  --provider anfibius \
  --format json \
  --pretty \
  --output-dir exportacion-anfibius
```

## Salidas, `stdout` y `stderr`

- Los datos solicitados con `--output -` se escriben únicamente en `stdout`.
- Errores y el resumen final se escriben en `stderr`, por lo que es seguro redirigir los datos.
- El resumen incluye la duración total de scraping y escritura, con segundos, minutos u horas.
- CSV usa UTF-8 sin BOM, encabezado canónico, `TRUE`/`FALSE` y celda vacía para `null`.
- JSON es un array raíz; `--pretty` sólo modifica espacios y saltos de línea.
- Los archivos se escriben mediante un temporal y se publican al terminar.
- Ningún archivo existente se reemplaza sin `--overwrite`.

Ejemplo de redirección:

```bash
python -m scraper_cli reviews \
  --config config.toml \
  --provider competidor_demo \
  --format json \
  --output - \
  > reviews.json 2> ejecucion.log
```

## Precedencia de valores operativos

| Valor | Precedencia |
| --- | --- |
| Cantidad máxima | `--limit` → `[defaults].max_items`. |
| Timeout | `--timeout` → timeout de fuente → `[defaults].timeout_seconds`. |
| País de reseñas | `--country` → país de fuente → `[defaults].country_code`. |
| Formato | `--format`; no se infiere de la extensión. |
| Selección | filtros CLI → sólo fuentes con `enabled = true`. |
| Archivo | `--output` → carpeta global + nombre configurado para el proveedor. |
| Directorio de `all` | `--output-dir` → `[output].directory`. |

Opciones internas como `retry_limit`, `request_delay_seconds`, `max_pages` o configuraciones
específicas del adapter se definen en TOML y no tienen un override CLI.

## Códigos de salida

| Código | Significado |
| --- | --- |
| `0` | Todas las fuentes seleccionadas terminaron correctamente. |
| `1` | Error inesperado de ejecución. |
| `2` | Argumentos o configuración inválidos; `argparse` también usa este código. |
| `3` | Fallaron todas las fuentes intentadas. |
| `4` | Éxito parcial: al menos una fuente funcionó y otra falló. |
| `5` | Error de salida, contrato inválido o archivo existente sin `--overwrite`. |

Por defecto, un fallo se aísla y las siguientes fuentes continúan. Los registros obtenidos de
fuentes exitosas se conservan y el proceso devuelve `4`. Usa `--fail-fast` cuando un resultado
parcial no sea aceptable para el proceso que invoca la CLI.

## Diagnóstico recomendado

1. Ejecuta `validate-config`.
2. Comprueba la clave con `list-adapters`.
3. Reduce la ejecución con un solo `--provider` y un `--limit` pequeño.
4. Confirma que la fuente esté activa y que `--source` coincida exactamente.
5. Añade `--verbose` y revisa `stderr` y el código de salida.
6. Aumenta límites o timeouts sólo después de identificar qué límite se alcanzó.

Errores frecuentes:

- `El archivo ya existe`: cambia la ruta o añade `--overwrite` conscientemente.
- `fuente activa inexistente`: el nombre no coincide, la fuente está deshabilitada o pertenece a
  otro tipo.
- `Se alcanzó max_pages`: incrementa el límite TOML o reduce `--limit`.
- timeout de Playwright: revisa conectividad, Chromium y los límites específicos del adapter.
- salida vacía con código `0`: las fuentes seleccionadas terminaron correctamente pero no
  publicaron registros compatibles.

La CLI no evade CAPTCHA, autenticación ni protecciones anti-bot. Revisa autorización, términos,
privacidad y límites del sitio antes de activar una fuente real.
