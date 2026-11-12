# Documentación de Market Watch

Este directorio reúne la documentación técnica y operativa del proyecto. Empieza por el documento que corresponda a la pregunta que quieres resolver; no es necesario leerlos en orden.

Las guías se agrupan por propietario: [manuales de usuario](manuales/README.md),
[desarrollo](development/README.md), [operación](operations/README.md), [CLI](cli/README.md),
[datos](data/README.md) y [producto](product/README.md). La
[gestión del proyecto](project/README.md) conserva métricas y estimaciones. Arquitectura, decisiones
y seguimiento permanecen en esta raíz como puntos canónicos compartidos.

## Referencias principales

| Necesidad | Documento | Contenido |
| --- | --- | --- |
| Usar la aplicación web | [Manual del portal](manuales/manual-portal-principal.md) | Acceso, roles, pantallas, controles, flujos frecuentes y diagnóstico. |
| Administrar datos y usuarios | [Manual de Django Admin](manuales/manual-django-admin.md) | Uso seguro, permisos y referencia de todos los modelos registrados. |
| Entender las tecnologías | [Stack tecnológico](TECHNOLOGY_STACK.md) | Dependencias, herramientas, versiones, uso real y justificación. |
| Entender el diseño | [Arquitectura](ARCHITECTURE.md) | Límites, capas, módulos, procesos, flujos y decisiones. |
| Encontrar dónde hacer un cambio | [Estructura del repositorio](REPOSITORY_STRUCTURE.md) | Propósito de archivos raíz y carpetas relevantes. |
| Empezar desarrollo desde cero | [Desarrollo por sistema](development/README.md) | Recorridos Linux/Windows, Django, scheduler y assets. |
| Preparar y usar el entorno local | [Desarrollo](development/DEVELOPMENT.md) | Instalación, ejecución, usuarios, datos y flujo diario. |
| Configurar variables de entorno | [Variables de entorno](development/ENVIRONMENT_VARIABLES.md) | Tipos, defaults, ejemplos, seguridad, rutas Linux/Windows y alcance Docker. |
| Traducir comandos entre sistemas | [Linux y Windows](development/WINDOWS_LINUX.md) | Binarios del entorno, rutas, PowerShell, Bash y alcance de producción. |
| Crear un integrador | [Agregar un provider](development/ADDING_A_PROVIDER.md) | Metodología aislada, contrato, fixtures y pruebas. |
| Agregar una fuente de reseñas | [Fuentes de reseñas](development/ADDING_A_REVIEW_SOURCE.md) | Contrato, registro, límites, legalidad y pruebas offline. |
| Exportar reseñas | [Esquema CSV](data/REVIEW_CSV_SCHEMA.md) | Las 18 columnas, nulos, formatos y filtros canónicos. |
| Usar la CLI sin Django | [Arquitectura CLI](cli/CLI_ARCHITECTURE.md) | Límites, configuración, adapters y flujo sin base de datos. |
| Empezar con la CLI | [CLI: leer primero](cli/CLI_LEER_PRIMERO.md) | Preparación y primera exportación recomendada paso a paso. |
| Consultar comandos y opciones de la CLI | [Uso de la CLI](cli/CLI_USAGE.md) | Subcomandos, parámetros, ejemplos, salidas y códigos de retorno. |
| Configurar la CLI | [Configuración TOML](cli/CLI_CONFIG.md) | Tablas, campos, tipos, defaults, adapters y precedencia. |
| Interpretar exportaciones CLI | [Contratos CLI](cli/CLI_OUTPUT_SCHEMAS.md) | Columnas, tipos, nulos y versiones de planes, características y reseñas. |
| Ejecutar el pipeline posterior | [Pipeline de datos](data/DATA_PIPELINE.md) | Etapas raw/clean/normalized, detección, CLI y solución de errores. |
| Operar el pipeline persistente | [Pipeline Django](data/DJANGO_PIPELINE.md) | Configuraciones versionadas, scheduler secuencial, importación, publicación y regeneración SQLite. |
| Usar y configurar el dashboard | [Dashboard competitivo](product/DASHBOARD.md) | Presets, filtros, marca, fórmulas, permisos, datos DEMO y diagnóstico. |
| Limpiar archivos extraídos | [Limpieza de datos](data/DATA_CLEANING.md) | Reglas conservadoras, duplicados, nulos y API/CLI. |
| Normalizar para análisis | [Transformación de datos](data/DATA_TRANSFORMATION.md) | Tipos, esquemas finales, derivaciones e incidencias. |
| Consolidar características equivalentes | [Reglas de equivalencia](data/FEATURE_EQUIVALENCE_RULES.md) | Schema JSON, reglas por competidor, reductores, derivados, fallback y reporte. |
| Auditar las equivalencias actuales | [Análisis de equivalencias](data/FEATURE_EQUIVALENCE_ANALYSIS.md) | Matriz por competidor, cobertura obtenida y conceptos pendientes de decisión manual. |
| Entregar la CLI | [Distribución CLI](cli/CLI_DISTRIBUTION.md) | Builder allowlist, manifiesto e instalación aislada. |
| Instalar producción desde cero | [Producción](operations/PRODUCTION.md) | Secuencias Linux/Windows, salidas esperadas, monitoreo, detención y actualización. |
| Desplegar | [Producción con Nginx](operations/DEPLOYMENT_NGINX.md) | Docker Compose, Nginx, TLS, actualización y rollback. |
| Operar el servicio | [Operación](operations/OPERATIONS.md) | Scheduler, salud, backup, restauración e incidentes. |
| Revisar controles | [Seguridad](operations/SECURITY.md) | Modelo de amenazas, SSRF, secretos y evidencia. |
| Entender límites de recursos | [Uso de recursos](operations/RESOURCE_USAGE.md) | Concurrencia y comandos costosos. |
| Consultar esfuerzo acumulado | [Estimación de esfuerzo](project/PROJECT_EFFORT.md) | Línea base, rango, metodología y registro incremental. |

## Decisiones y seguimiento

- [Reglas para colaboradores y agentes](../AGENTS.md): protección de datos, arquitectura, dependencias, pruebas y condiciones de cierre.
- [Decisiones de arquitectura](DECISIONS.md): ADR breves que conservan el contexto y las consecuencias de decisiones relevantes.
- [Plan de implementación](IMPLEMENTATION_PLAN.md): tareas verificables y dependencias del trabajo.
- [Progreso](PROGRESS.md): último checkpoint operativo e historial corto.

`ARCHITECTURE.md` describe el diseño vigente; `DECISIONS.md` explica por qué se eligieron sus decisiones principales. Si ambos parecen contradecirse, el código es la realidad ejecutable y la discrepancia debe corregirse en la misma entrega.

## Fuentes de verdad

Para evitar que la documentación copie datos que después quedan obsoletos:

| Tema | Fuente de verdad |
| --- | --- |
| Dependencias Python y rangos | `pyproject.toml`; el entorno se reproduce con `requirements.lock`; el runtime distribuible está en `cli_dist/requirements.txt`. |
| Dependencias frontend y versiones exactas | `frontend/package.json` y `frontend/pnpm-lock.yaml`. |
| Variables configurables | `.env.example`, `.env.production.example` y `src/config/settings/`. |
| Servicios y volúmenes | `compose.yaml`. |
| Imagen de producción | `Dockerfile`. |
| Comandos habituales | `Makefile` y `scripts/`. |
| Rutas HTTP | `src/config/urls.py` y módulos `*_urls.py`/`urls.py` de las aplicaciones. |
| Esquema de datos | Modelos y migraciones bajo `src/apps/*/`. |

## Regla de mantenimiento

Una entrega debe actualizar también:

- `TECHNOLOGY_STACK.md` si añade, elimina o cambia el propósito de una dependencia o herramienta;
- `ARCHITECTURE.md` y, si hay una decisión con alternativas, `DECISIONS.md` cuando cambia un límite, proceso o flujo;
- `REPOSITORY_STRUCTURE.md` si crea una carpeta de primer nivel o cambia la responsabilidad de una carpeta importante;
- las guías de desarrollo, despliegue u operación si modifica comandos o variables;
- `project/PROJECT_EFFORT.md` en toda entrega que modifique el repositorio;
- `IMPLEMENTATION_PLAN.md` y `PROGRESS.md` para dejar un checkpoint reanudable.

Ejecuta `make docs-check` para comprobar los archivos requeridos, la configuración de Compose, la sintaxis de scripts y los enlaces Markdown locales.
