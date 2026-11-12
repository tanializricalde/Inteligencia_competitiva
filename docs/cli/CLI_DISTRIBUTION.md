# Distribución de la CLI

## Construcción

Desde la raíz del repositorio:

```bash
.venv/bin/python scripts/build_cli_dist.py --output dist/scraper-cli
```

En Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_cli_dist.py --output .\dist\scraper-cli
```

Un destino existente requiere `--overwrite`. El builder rechaza destino vacío, `/`, el home y la
raíz del repositorio. Construye primero en un temporal hermano, valida y publica al final. Sólo usa
una allowlist; no copia el proyecto para borrar archivos posteriormente ni sigue symlinks.

## Plantillas versionadas

El builder toma cuatro archivos fuente de `cli_dist/`: `requirements.txt`, `README.md`,
`THIRD_PARTY_NOTICES.md` y `run.py`. Aunque el nombre conserva compatibilidad histórica, esa carpeta
no es el artefacto construido. Sus cuatro plantillas se versionan mediante excepciones explícitas
en `.gitignore`; la salida regenerable se escribe bajo `dist/`.

`cli_dist/requirements.txt` contiene únicamente el runtime independiente. No sustituye a
`requirements.lock`: este último reproduce el proyecto completo, Django y herramientas de
desarrollo. El builder falla antes de publicar si falta cualquier plantilla permitida.

## Contenido

```text
scraper-cli/
├── scraper_cli/                 # argumentos, TOML, ejecución y exportadores
├── scraping_core/               # DTO, parsers y adapters puros
├── data_pipeline/               # perfiles, detección, políticas, reportes e I/O
├── data_cleaning/               # API y CLI de limpieza
├── data_transformation/         # API y CLI de normalización final
├── feature_rules/               # ejemplo y JSON Schema de equivalencias
├── docs/                        # documentación incluida
│   ├── cli/                     # inicio, uso, TOML, contratos y arquitectura
│   ├── data/                    # pipeline, limpieza, transformación y equivalencias
│   └── development/             # equivalencias Bash/PowerShell y rutas
├── config.example.toml          # demo offline editable
├── requirements.txt             # dependencias exclusivas de esta CLI
├── README.md                    # guía autocontenida para el destinatario
├── THIRD_PARTY_NOTICES.md
├── MANIFEST.json                # SHA-256 y tamaño, orden determinista
└── run.py                       # entrada alternativa
```

El manifiesto enumera todos los archivos de contenido; no se autoenumera porque su hash sería
recursivo. No hay Django, modelos, migraciones, base, `.env`, credenciales, cookies, `.git`, entorno
virtual, caches, node_modules, fixtures privadas ni navegador descargado.

## Validaciones previas a publicar

1. parseo y compilación AST de todo Python;
2. rechazo de imports `django`, `apps`, settings web, modelos, migraciones o repositorios;
3. `--help`, `list-adapters` y `validate-config` desde la carpeta temporal;
4. ejecución offline de `all` con la configuración de demostración;
5. limpieza y transformación real del JSON de reseñas recién generado;
6. presencia del schema, ejemplo y guía de equivalencias en la allowlist;
7. `PYTHONPATH` eliminado y `DATABASE_URL` deliberadamente inválida;
8. generación final de hashes y tamaños.

La copia funciona fuera del repositorio porque sus cinco paquetes están en su propia raíz. El
builder no modifica imports durante el copiado.

## Instalación en otra máquina

Consulta el `README.md` de la distribución. En resumen, se requiere Python 3.12+, un entorno virtual
opcional y `python -m pip install -r requirements.txt`. Chromium se instala por separado con
`python -m playwright install chromium` sólo si se usará el adapter Playwright. No se generan ni
entregan ejecutables, DLL, wheels o binarios propios.

## Reproducibilidad y actualización

Con el mismo árbol fuente, los archivos copiados y `MANIFEST.json` son deterministas; timestamps del
filesystem no forman parte del manifiesto. Compara hashes antes de entregar. Para una actualización,
reconstruye en una ruta nueva o usa `--overwrite`, valida el manifiesto y conserva la versión previa
como rollback externo hasta comprobar los comandos reales.
