# Comandos equivalentes en Linux y Windows

La aplicación y la CLI funcionan con Python 3.12 o 3.13 en Linux y Windows. Los ejemplos con
`bash` usan Linux; los ejemplos con `powershell` usan PowerShell 7 o Windows PowerShell. Ejecuta
siempre los comandos desde la raíz del repositorio o del distribuible, según indique la guía.

## Rutas y comandos básicos

| Operación | Linux (Bash) | Windows (PowerShell) |
| --- | --- | --- |
| Python del entorno | `.venv/bin/python` | `.\.venv\Scripts\python.exe` |
| Pip del entorno | `.venv/bin/python -m pip` | `.\.venv\Scripts\python.exe -m pip` |
| Playwright | `.venv/bin/python -m playwright` | `.\.venv\Scripts\python.exe -m playwright` |
| Separador de ruta | `carpeta/archivo.csv` | `carpeta\archivo.csv` |
| Copiar archivo | `cp origen destino` | `Copy-Item origen destino` |
| Crear carpeta | `mkdir -p data` | `New-Item -ItemType Directory -Force data` |
| Continuar una línea | `\` | acento grave: `` ` `` |
| Variable temporal | `NOMBRE=valor comando` | `$env:NOMBRE='valor'; comando` |

Python acepta normalmente `/` en rutas de Windows. En TOML se recomienda
`directory = "salidas/csv"` en ambos sistemas. Si se usan barras invertidas, una cadena TOML
básica debe escaparlas (`"salidas\\csv"`), o puede usarse una cadena literal
(`'salidas\csv'`). Las rutas relativas se resuelven desde la carpeta actual del terminal, no desde
la ubicación de `config.toml`.

## Crear el entorno

Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m playwright install chromium
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m playwright install chromium
```

No es necesario activar el entorno si se invoca el binario indicado. Si se activa, `python` puede
reemplazar esas rutas durante esa terminal.

## Ejecutar Django en desarrollo

Linux, en dos terminales:

```bash
.venv/bin/python manage.py runserver
.venv/bin/python manage.py run_scheduler
```

Windows PowerShell, también en dos terminales:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe manage.py run_scheduler
```

En ambos casos `Ctrl+C` detiene cada proceso sin borrar datos. Los scripts `.sh` y el `Makefile`
son utilidades para Bash/Linux; en Windows nativo usa `Makefile.ps1` y
`scripts/dev-bootstrap.ps1`, o los comandos Python, pnpm y Docker equivalentes documentados aquí y
en la guía de desarrollo del repositorio completo. Docker Desktop proporciona
`docker compose` con la misma sintaxis en ambos sistemas.

## Ejecutar la CLI

Linux:

```bash
.venv/bin/python -m scraper_cli reviews \
  --config config.toml \
  --provider siigo_ec \
  --output salidas/resenas.csv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m scraper_cli reviews `
  --config .\config.toml `
  --provider siigo_ec `
  --output .\salidas\resenas.csv
```

Las opciones y contratos son idénticos. Sólo cambia el shell, la ruta del ejecutable y, si se
prefiere, el separador de directorios.

## Producción

Linux con Nginx/Certbot es la ruta productiva canónica. Windows puede ejecutar los mismos
contenedores Linux con Docker Desktop mediante `scripts\deploy-production.ps1`, pero requiere un
proxy TLS del host y arranque automático de ambos componentes. No ejecutes los archivos de Nginx
directamente en Windows. Consulta [Producción desde cero](../operations/PRODUCTION.md) para los dos
recorridos, monitoreo, detención y actualización.
