# Scraper CLI independiente

Requiere Python 3.12 o superior. Este paquete no usa Django ni una base de datos.

## Instalación

Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Playwright sólo es necesario para adapters dinámicos. Instala Chromium cuando vayas a usarlos:

```bash
.venv/bin/python -m playwright install chromium
```

En Windows usa `.\.venv\Scripts\python.exe -m playwright install chromium`. La tabla completa de
equivalencias está en `docs/development/WINDOWS_LINUX.md`.

Copia `config.example.toml`, configura proveedores y revisa el User-Agent de contacto. La
referencia de tablas, campos, tipos, defaults y precedencia está en `docs/cli/CLI_CONFIG.md`. No guardes
secretos en TOML; un adapter que los necesite debe recibirlos mediante variables de entorno.

## Uso de scraping

Si es tu primera ejecución, comienza por `docs/cli/CLI_LEER_PRIMERO.md`. La referencia detallada está
en `docs/cli/CLI_USAGE.md`; cada subcomando también tiene `--help`.

```bash
python -m scraper_cli --help
python -m scraper_cli list-adapters
python -m scraper_cli validate-config --config config.example.toml
python -m scraper_cli plans --config config.example.toml --output plans.csv
python -m scraper_cli reviews --config config.example.toml --format json --output reviews.json
python -m scraper_cli all --config config.example.toml --output-dir output
```

`--provider` y `--source` pueden repetirse. `--limit`, `--timeout` y `--country` sustituyen valores
operativos; `--fail-fast` detiene la ejecución después del primer fallo. Ningún archivo se reemplaza
sin `--overwrite`. Los datos van al archivo o stdout y el resumen va a stderr.

CSV usa UTF-8 sin BOM, encabezados canónicos, `TRUE`/`FALSE` y campos vacíos para ausencias. JSON
usa un arreglo raíz y `null`. Consulta `docs/cli/CLI_OUTPUT_SCHEMAS.md`.

## Limpieza y transformación posteriores

La distribución incluye dos comandos locales adicionales:

```bash
python -m data_cleaning output/reviews.csv --output clean/reviews.csv
python -m data_transformation clean/reviews.csv --output normalized/reviews.csv --report reports/reviews.json
python -m data_cleaning output --output-dir clean
python -m data_transformation clean --output-dir normalized --format json
```

En Windows PowerShell reemplaza `python` por `.\.venv\Scripts\python.exe` y usa `\` en las rutas.
Ambos comandos infieren `review`, `plan` o `feature` usando ruta y columnas; una señal ambigua se
resuelve con `--type`. También aceptan múltiples archivos o carpetas: sin `--type`, usa
`--output-dir` para obtener un consolidado `reviews`, `plans` y `features`; los nombres se cambian
con `--review-filename`, `--plan-filename` y `--feature-filename`. Consulta
`docs/data/DATA_PIPELINE.md`, `docs/data/DATA_CLEANING.md` y `docs/data/DATA_TRANSFORMATION.md`.

Limpieza elimina columnas totalmente vacías y registra políticas numéricas. Ambos comandos
aceptan `--report`; transformación de características acepta `--wide-output` y conserva como canónica
la tabla larga.

Para consolidar descripciones equivalentes en la vista ancha usa la configuración versionada:

```bash
python -m data_transformation clean/features.csv \
  --output normalized/features.csv \
  --wide-output normalized/features-wide.csv \
  --feature-rules feature_rules/feature-equivalence.example.json \
  --feature-rules-report reports/feature-equivalence.json
```

El schema, el ejemplo y la referencia completa se distribuyen en `feature_rules/` y
`docs/data/FEATURE_EQUIVALENCE_RULES.md`. Sin `--feature-rules` se conserva el pivote histórico.

## Códigos de salida

- `0`: éxito completo.
- `1`: error inesperado.
- `2`: argumentos, configuración o datos inválidos.
- `3`: todas las fuentes de scraping fallaron.
- `4`: archivo producido con advertencias o scraping parcial.
- `5`: error de escritura o contrato de salida.

Respeta robots.txt, términos del sitio, privacidad y límites de acceso. La herramienta no evade
CAPTCHA, autenticación ni protecciones anti-bot.
