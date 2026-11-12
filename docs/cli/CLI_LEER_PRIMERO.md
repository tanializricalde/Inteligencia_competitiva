# CLI: leer primero

Esta es la ruta recomendada para realizar una primera exportación con la CLI. La herramienta
ejecuta scrapers de planes y reseñas sin utilizar Django ni una base de datos.

Para conocer todas las opciones consulta [Uso de la CLI](CLI_USAGE.md). Para modificar proveedores,
fuentes, tiempos o paginación consulta [Configuración TOML](CLI_CONFIG.md).
Los bloques siguientes usan Bash/Linux. Para ejecutar los mismos pasos en PowerShell, incluida la
ruta `.\.venv\Scripts\python.exe`, consulta [Linux y Windows](../development/WINDOWS_LINUX.md).

## 1. Preparar la CLI

Desde la carpeta del distribuible:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

Chromium es necesario para las fuentes basadas en Playwright, incluidas las reseñas de Google
Maps. En Windows, reemplaza `.venv/bin/python` por `.\.venv\Scripts\python.exe`.

Copia `config.example.toml` si deseas conservar el ejemplo sin cambios:

```bash
cp config.example.toml config.toml
```

En PowerShell usa `Copy-Item config.example.toml config.toml`.

Revisa en `config.toml` las URLs y el valor `enabled` de cada fuente antes de continuar. No actives
fuentes que no estés autorizado a consultar.

También revisa `[output].directory`, `plans_filename` y `reviews_filename`. Para un solo proveedor
puedes omitir `--output`; la CLI combinará esa carpeta y el nombre configurado. Una ruta relativa
parte de la carpeta actual del terminal.

## 2. Validar la configuración

La validación no ejecuta scrapers ni abre el navegador:

```bash
.venv/bin/python -m scraper_cli validate-config --config config.toml
```

También puedes comprobar los adapters disponibles:

```bash
.venv/bin/python -m scraper_cli list-adapters
```

Si trabajas desde el repositorio y ya tienes su entorno virtual activo, puedes usar simplemente
`python -m scraper_cli`. En el resto de esta guía se usa esa forma abreviada.

## 3. Estrategia recomendada

Ejecuta primero los planes y después las reseñas de cada proveedor por separado. Google Maps puede
responder de manera variable; separar las ejecuciones permite reintentar únicamente la fuente que
falló sin repetir exportaciones correctas.

La CLI crea los directorios padre de los archivos cuando sea necesario.

### 3.1 Exportar planes y características

```bash
python -m scraper_cli plans \
  --config config.toml \
  --output csv/planes.csv \
  --features-output csv/plan_caracteristicas.csv \
  --overwrite
```

Este comando ejecuta todas las fuentes de planes activas. Para limitarlo a un proveedor añade, por
ejemplo, `--provider siigo_ec`.

### 3.2 Exportar reseñas de Siigo

```bash
python -m scraper_cli reviews \
  --config config.toml \
  --provider siigo_ec \
  --limit 1000 \
  --output csv/resenas_siigo.csv \
  --overwrite
```

### 3.3 Exportar reseñas de Anfibius

```bash
python -m scraper_cli reviews \
  --config config.toml \
  --provider anfibius \
  --limit 1000 \
  --output csv/resenas_anfibius.csv \
  --overwrite
```

### 3.4 Exportar reseñas de Perseo

```bash
python -m scraper_cli reviews \
  --config config.toml \
  --provider perseo \
  --limit 1000 \
  --output csv/resenas_perseo.csv \
  --overwrite
```

`--limit` es el máximo por fuente, no una garantía de que el sitio publique esa cantidad. El
resultado también depende de `max_pages`, `page_size`, reintentos y límites de carga configurados
en el TOML.

## 4. Ejecutar todo en un solo comando

También es posible ejecutar todos los planes y reseñas activos:

```bash
python -m scraper_cli all \
  --config config.toml \
  --format csv \
  --output-dir csv \
  --overwrite
```

El comando crea:

```text
csv/
├── plans.csv
├── plan_features.csv
└── reviews.csv
```

Esta variante es cómoda para una ejecución programada, pero no es la mejor opción para diagnosticar
la primera carga. Si una fuente de Google Maps falla, el comando puede terminar con éxito parcial y
un código distinto de cero aunque otras fuentes hayan generado datos válidos.

## 5. Interpretar el resultado

Al finalizar, la CLI escribe un resumen en `stderr`:

```text
Resumen: intentadas=3 exitosas=2 fallidas=1 registros=120 salidas=... duración=8m 12.40s código=4
```

| Código | Significado                                               | Acción sugerida                                                |
| ------ | --------------------------------------------------------- | -------------------------------------------------------------- |
| `0`    | Todas las fuentes seleccionadas terminaron correctamente. | Revisa los archivos generados.                                 |
| `1`    | Ocurrió un error inesperado.                              | Revisa el tipo y mensaje del error antes de reintentar.        |
| `2`    | Argumentos o configuración inválidos.                     | Ejecuta `validate-config` y revisa el comando.                 |
| `3`    | Fallaron todas las fuentes intentadas.                    | Corrige o reintenta la fuente indicada.                        |
| `4`    | Algunas fuentes funcionaron y otras fallaron.             | Conserva los resultados válidos y reintenta sólo las fallidas. |
| `5`    | No se pudo generar la salida.                             | Revisa rutas o utiliza `--overwrite` conscientemente.          |

Los mensajes que comienzan con `ERROR proveedor/fuente` identifican exactamente qué fuente debe
reintentarse. No combines manualmente archivos hasta comprobar sus encabezados; todos deben
corresponder al mismo contrato documentado en [Esquemas de salida](CLI_OUTPUT_SCHEMAS.md).

## 6. Ajustar una carga lenta o incompleta

Empieza con una ejecución pequeña antes de solicitar cientos de registros:

```bash
python -m scraper_cli reviews \
  --config config.toml \
  --provider anfibius \
  --limit 20 \
  --output csv/prueba_anfibius.csv \
  --overwrite
```

Los controles se dividen en dos grupos:

- opciones del comando, como `--limit`, `--timeout`, `--provider` y `--fail-fast`, descritas en
  [Uso de la CLI](CLI_USAGE.md);
- valores del TOML, como `max_pages`, `page_size`, `retry_limit`, `scroll_pause_ms` y
  `max_load_seconds`, descritos en [Configuración TOML](CLI_CONFIG.md).

No aumentes todos los límites a la vez. Primero identifica si el error corresponde a navegación,
paginación, carga dinámica o escritura. Las fuentes de Google Maps están acotadas por tiempo,
desplazamientos y reintentos: pueden tardar, pero no deberían quedar esperando indefinidamente.

## 7. Archivos de referencia

| Documento                                      | Cuándo consultarlo                                            |
| ---------------------------------------------- | ------------------------------------------------------------- |
| [CLI_USAGE.md](CLI_USAGE.md)                   | Parámetros, subcomandos, precedencia, ejemplos y diagnóstico. |
| [CLI_CONFIG.md](CLI_CONFIG.md)                 | Estructura completa y campos de `config.toml`.                |
| [CLI_OUTPUT_SCHEMAS.md](CLI_OUTPUT_SCHEMAS.md) | Columnas, tipos, nulos y versiones de contratos.              |
| [CLI_DISTRIBUTION.md](CLI_DISTRIBUTION.md)     | Construcción, contenido y validación del distribuible.        |

`--overwrite` reemplaza archivos existentes. Omítelo cuando quieras que la CLI se detenga antes de
sobrescribir una exportación previa.
