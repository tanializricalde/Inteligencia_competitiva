# Estructura del repositorio

## Lectura rápida

```text
.
├── docs/                 documentación de usuario, técnica y operativa
├── cli_dist/             recursos autocontenidos de la distribución CLI
├── deploy/               configuraciones Nginx versionadas
├── frontend/             fuentes y toolchain de activos web
├── feature_rules/        ejemplo y JSON Schema de equivalencias de características
├── scripts/              automatización segura de desarrollo/despliegue
├── src/                  código ejecutable Django y activos compilados
├── tests/                pruebas y fixtures offline
├── codex/staging/        continuidad extensa y propuestas sin efecto
├── config.example.toml configuración local y demo offline de la CLI
├── Dockerfile            construcción reproducible de la imagen
├── compose.yaml          topología de servicios de un solo host
├── Makefile              interfaz de comandos frecuentes
├── Makefile.ps1  interfaz equivalente para PowerShell
├── AGENTS.md             reglas operativas para colaboradores y agentes
├── manage.py             entrada de administración Django
└── pyproject.toml        paquete Python y herramientas de calidad
```

## Archivos de la raíz

| Ruta | Propósito | Cuándo modificarla |
| --- | --- | --- |
| `README.md` | Presentación e inicio rápido; enlaza el índice de documentación. | Cuando cambia la experiencia inicial o los comandos principales. |
| `AGENTS.md` | Reglas de seguridad, arquitectura, pruebas y cierre para cualquier colaborador. | Cuando una práctica operativa cambia; debe permanecer alineado con Makefile y documentación. |
| `config.example.toml` | Configuración validable y demostración offline de la CLI independiente. | Al añadir adapters o cambiar su contrato local. |
| `manage.py` | Ejecuta comandos Django y añade `src/` al path del proyecto. | Rara vez; los comandos propios viven dentro de una app. |
| `pyproject.toml` | Metadatos, rangos de dependencias Python y configuración de pytest/Ruff. | Al cambiar dependencias, versión mínima o reglas de herramientas. |
| `requirements.in` | Entrada humana para el conjunto de dependencias instalables. | Junto con `pyproject.toml` cuando cambia el stack Python. |
| `requirements.lock` | Resolución concreta usada por setup y Docker. Está exceptuada de la regla general `*.lock` porque un clon limpio debe poder ejecutar setup y construir Docker. | Regenerar de manera deliberada con `make lock` después de validar dependencias. No editar a mano. |
| `Makefile` | Alias conservadores para setup, pruebas, assets, Docker, documentación y operación. | Cuando un flujo repetido necesita una interfaz estable. |
| `Makefile.ps1` | Tareas equivalentes para desarrollo y validación en PowerShell sin depender de GNU Make. | Junto con `Makefile` cuando cambia un flujo multiplataforma. |
| `.env.example` | Variables seguras de ejemplo para desarrollo, documentadas en [Variables de entorno](development/ENVIRONMENT_VARIABLES.md). | Al añadir o retirar configuración común. Nunca incluir secretos reales. |
| `.env.production.example` | Contrato productivo y valores seguros de referencia, cubiertos por la misma [referencia](development/ENVIRONMENT_VARIABLES.md). | Cuando cambia el despliegue o el hardening. |
| `.gitignore` | Excluye secretos, datos, entornos, cachés y artefactos locales. | Cuando aparece un artefacto regenerable o sensible nuevo. |
| `.dockerignore` | Reduce el contexto de build y evita copiar archivos locales/sensibles. | Cuando cambia lo necesario para construir la imagen. |
| `Dockerfile` | Build multi-stage: compila frontend, instala Python/Chromium, recoge estáticos y ejecuta como usuario no root. | Cuando cambia el runtime o la composición de la imagen. |
| `compose.yaml` | Define `web`, `scheduler`, `mailpit`, red implícita y volúmenes persistentes. | Cuando cambia la topología de una instalación de un host. |

`data/`, `evidence/`, `staticfiles/`, `.venv/`, `.env`, `.coverage`, cachés, `scheduler.lock` y `frontend/node_modules/` son estado local o generado: no son fuente editable y no deben versionarse.

## `docs/`: documentación mantenible por audiencia

- `manuales/`: manual funcional del portal y manual seguro de Django Admin para usuarios y
  administradores;
- `development/`: preparación y trabajo diario en Linux/Windows;
- `operations/`: producción, despliegue, monitoreo, respaldo y seguridad;
- `cli/`: uso, configuración, contratos y distribución de la CLI independiente;
- `data/`: limpieza, transformación, equivalencias y pipeline persistente;
- `product/`: comportamiento funcional especializado del producto;
- `project/`: estimaciones y seguimiento administrativo.

Arquitectura, decisiones, plan y progreso permanecen directamente en `docs/` porque atraviesan
todas las audiencias. El índice canónico es [`docs/README.md`](README.md).

## `src/`: aplicación Django y paquetes independientes

### Núcleo y CLI independientes

- `src/scraping_core/`: DTO, protocolos, datos puros, conversiones canónicas indispensables, seguridad y adapters reutilizados por la web y la CLI; no importa Django.
- `src/scraper_cli/`: configuración TOML, comandos, orquestación, mappers y exportadores sin base de datos.
- `src/data_pipeline/`: perfiles, detección, políticas numéricas, reportes, I/O tabular y mappers de contratos compartidos.
- `src/data_cleaning/`: API y CLI que corrigen calidad, eliminan columnas vacías y auditan políticas.
- `src/data_transformation/`: API y CLI que convierten tipos y agregan vistas analíticas trazables.
- `src/data_transformation/feature_rules/`: carga, valida y ejecuta equivalencias configurables para la vista ancha de características.
- `cli_dist/`: cuatro plantillas versionadas —README, dependencias mínimas, avisos y launcher— copiadas por la allowlist; no es la salida construida y el código se toma de `src/`.
- `scripts/build_cli_dist.py`: construye, valida y publica la carpeta distribuible con manifiesto.

El proyecto principal usa `requirements.lock`. El archivo `cli_dist/requirements.txt` sólo pertenece
al paquete independiente publicado en `dist/`; no debe moverse a la raíz ni generarse con el freeze
completo del entorno.

`feature_rules/` contiene la configuración JSON ejemplo y el JSON Schema versionado que también
se copian al distribuible CLI. No contiene código ejecutable.


### Configuración global

```text
src/config/
├── settings/
│   ├── base.py          configuración compartida y variables de entorno
│   ├── development.py   DEBUG y estáticos simples para desarrollo
│   ├── production.py    HTTPS, cookies y cabeceras seguras
│   └── test.py          DB en memoria, correo local y hashing rápido
├── urls.py              composición de rutas públicas, auth, admin y market
├── wsgi.py              entrada usada por Gunicorn
└── asgi.py              entrada disponible para servidores ASGI futuros
```

La configuración común debe vivir en `base.py`; los archivos de entorno sólo expresan diferencias. Una variable nueva también debe documentarse en los `.env.*.example` adecuados.

### Aplicaciones

`src/apps/accounts/` contiene identidad y autorización:

- `models.py` y `managers.py`: usuario autenticado por correo normalizado;
- `backends.py`: reglas del backend de autenticación;
- `forms.py` y `admin.py`: formularios y administración coherentes con el usuario personalizado;
- `signals.py`: crea/actualiza los grupos Administrador, Operador y Analista después de migrar;
- `urls.py`: rutas propias relacionadas con cuenta;
- `migrations/`: historial versionado del esquema; no es código descartable.

`src/apps/market/` contiene el catálogo histórico y su presentación:

- `domain/`: normalización, hash estable, diferencias y reglas puras sin I/O;
- `models.py`: providers, planes, snapshots y cambios detectados;
- `dashboard_service.py`: resolución estricta o tolerante de vistas/filtros y datasets analíticos sobre publicaciones canónicas;
- `branding.py`: acceso cacheado al singleton y adaptadores de identidad para plantillas y Unfold;
- `validators.py`: validación binaria/dimensional y saneamiento estructural de SVG de marca;
- `presentation.py`: vistas de dashboard, fuentes, ejecuciones, comparación, historial y configuración;
- `actions.py`: acciones POST y solicitudes manuales separadas de las consultas;
- `forms.py`: validación de entradas de la interfaz;
- `web_urls.py`: rutas completas de la interfaz funcional;
- `urls.py` y `views.py`: superficie mínima/compatibilidad del dashboard; antes de ampliarla, revisa la composición efectiva en `config/urls.py`;
- `templatetags/`: helpers de presentación reutilizables;
- `admin.py` y `migrations/`: administración y evolución de datos.

`src/templates/market/dashboard.html`, `dashboard_settings.html` y
`src/static/images/dashboard-brand-default.svg` componen la experiencia configurable. La guía de
uso y mantenimiento está en `docs/product/DASHBOARD.md`.

`src/apps/scraping/` organiza orquestación e infraestructura:

```text
scraping/
├── application/
│   ├── dtos.py          contrato ProviderScraper, datos originales y campos canónicos tipados
│   ├── errors.py        errores tipados del pipeline
│   └── services.py      casos de uso de scraping y cola manual
├── infrastructure/
│   ├── providers/       adapters HTTPX, Playwright y parsers específicos como Siigo
│   ├── builtin.py       registro de adapters incluidos
│   ├── registry.py      resolución por adapter_key
│   ├── scheduler.py     jobs, lock, heartbeat y proceso de colas
│   ├── url_safety.py    validación contra SSRF y destinos privados
│   ├── evidence.py      persistencia/saneamiento de evidencia de fallo
│   └── sqlite.py        PRAGMA de integridad, espera y WAL
├── management/commands/
│   ├── run_scheduler.py proceso dedicado de trabajos
│   ├── backup_sqlite.py backup consistente de SQLite
│   └── seed_demo.py     fuentes de ejemplo deshabilitadas
├── models.py            fuente, ejecución, resultados, agenda y heartbeat
├── validators.py        validaciones reutilizables de configuración
├── admin.py             inspección/edición administrativa
└── migrations/          evolución del esquema de scraping
```

`src/apps/pipeline/` contiene la persistencia y operación canónicas nuevas:

- `models.py`: configuración/perfiles versionados, ejecuciones, snapshots, características largas,
  reseñas, artefactos y calidad;
- `application/orchestrator.py`: barreras globales, reintentos, reanudación y aislamiento;
- `application/importers.py`, `publication.py` y `queries.py`: importación atómica, publicación por
  proveedor y lecturas únicamente publicadas;
- `infrastructure/core_executor.py`: conecta los cores puros con artefactos y ORM sin ejecutar CLI;
- `management/commands/`: configuración, seed, ejecución, diagnóstico, importación y publicación;
- `views.py`/`urls.py`: matriz dinámica autenticada;
- `migrations/` y `admin.py`: esquema reproducible y operación.

`src/apps/notifications/` implementa la outbox de correo:
`src/apps/reviews/` conserva el dominio histórico de captura/enriquecimiento y presenta la UI de
reseñas. La UI y `application/export.py` proyectan hoy `pipeline.ReviewSnapshot` mediante
`application/published.py`; modelos, adapters y comandos antiguos permanecen para compatibilidad y
auditoría. No debe mezclarse con el DTO de planes.

- `models.py`: destinatarios y eventos persistentes con idempotencia;
- `services.py`: encolado y envío con reintento/control de estado;
- `admin.py`: inspección operativa;
- `migrations/`: esquema versionado.

### Plantillas y activos

`src/templates/` se divide por responsabilidad:

- `layouts/`: base HTML, shell autenticado y shell de autenticación;
- `components/`: mensajes y selector de tema compartidos;
- `market/`: páginas del producto;
- `registration/`: login, cambio y restablecimiento de contraseña;
- `notifications/`: variantes HTML/texto del correo.

`src/static/dist/` contiene la salida generada por Vite (`app.js`, `app.css`, fuentes e `manifest.json`). No edites esos archivos directamente: cambia `frontend/src/` y ejecuta `make assets`. `src/static/app.css` y `src/static/app.js` son entradas estáticas históricas/de compatibilidad; las plantillas principales consumen el bundle `dist` mediante el manifest.

## `frontend/`: fuentes de interfaz

| Ruta | Propósito |
| --- | --- |
| `frontend/src/app.scss` | Importa/personaliza Tabler y define los estilos del sitio. |
| `frontend/src/app.js` | Entrada JavaScript: HTMX, Chart.js y comportamiento global como el tema. |
| `frontend/vite.config.js` | Escribe el bundle y manifest en `src/static/dist/` con base `/static/dist/`. |
| `frontend/package.json` | Scripts, engines, gestor y dependencias directas. |
| `frontend/pnpm-lock.yaml` | Árbol exacto reproducible de paquetes. |
| `frontend/pnpm-workspace.yaml` | Configuración del workspace pnpm. |

## `tests/`: verificación por módulo

Las carpetas `tests/accounts/`, `tests/market/`, `tests/scraping/`, `tests/reviews/`, `tests/cli/` y `tests/notifications/` reflejan los módulos productivos. Las pruebas transversales de presentación, seguridad, salud y smoke pueden vivir en la raíz de `tests/`.

`tests/fixtures/providers/` contiene HTML y páginas JS locales que representan contratos de terceros. Deben ser mínimos, estar sanitizados y acompañar las pruebas del adapter; nunca deben contener sesiones, cookies ni datos reales sensibles.

La marca `playwright` separa casos que levantan Chromium. `make test` los excluye y `make test-playwright` los ejecuta explícitamente para controlar recursos.

## Operación, despliegue y continuidad

| Carpeta | Contenido |
| --- | --- |
| `deploy/` | Configuración Nginx de bootstrap HTTP y configuración final HTTPS. Se instala mediante la guía/script, no se edita directamente en el host como fuente primaria. |
| `scripts/` | Los bootstrap Bash/PowerShell preparan desarrollo; `deploy-production.sh` y `deploy-production.ps1` validan/despliegan en Linux/Windows; `check-nginx-config.sh` prueba Nginx Linux; `check_doc_links.py` valida enlaces; `build_cli_dist.py` crea la distribución allowlist y `generate_anfibius_recovery_fixture.py` reproduce el fixture inmutable de la migración histórica. |
| `docs/` | Índice, referencias técnicas, guías, ADR y checkpoints. Véase [el índice](README.md). |
| `docs/development/` | Arranque Linux/Windows, flujo diario y creación aislada de providers. |
| `docs/operations/` | Producción, Nginx, operación, seguridad y recursos. |
| `docs/cli/` | Uso, configuración, contratos y distribución de la CLI independiente. |
| `docs/data/` | Limpieza, transformación, equivalencias, persistencia y auditoría de módulos del pipeline. |
| `docs/product/` | Comportamiento y administración de superficies de producto. |
| `docs/project/` | Métricas de gestión, estimación histórica y registro incremental de esfuerzo. |
| `codex/staging/` | Handoffs extensos, reportes sanitizados y propuestas inactivas. No sustituye código, documentación oficial, plan ni progreso; su ciclo de vida está descrito en su propio README. |

## Dónde implementar cada cambio

| Cambio | Ubicación inicial |
| --- | --- |
| Regla de normalización/diff sin I/O | `src/apps/market/domain/` y `tests/market/`. |
| Campo persistente o restricción | `models.py` de la app propietaria + migración + pruebas. |
| Nuevo provider | `scraping/infrastructure/providers/`, `builtin.py`, fixture y `tests/scraping/`; sigue [la guía](development/ADDING_A_PROVIDER.md). |
| Cambio en CLI o contrato externo | `src/scraper_cli/`, `src/scraping_core/`, `tests/cli/` y las guías `CLI_*`. |
| Regla de limpieza o transformación | `src/data_*`, `tests/data_pipeline/` y las guías `DATA_*`. |
| Cambio en el pipeline | `scraping/application/services.py`, conservando I/O fuera de transacciones. |
| Página o formulario | `market/presentation.py`/`actions.py`/`forms.py`, `templates/market/` y pruebas de presentación. |
| Estilo o JavaScript global | `frontend/src/`; después `make assets`. |
| Notificación | `notifications/models.py`/`services.py` y plantillas `templates/notifications/`. |
| Frecuencia o worker local | `scraping/infrastructure/scheduler.py` y modelos de agenda. |
| Variable de entorno | settings, ambos ejemplos necesarios y guía correspondiente. |
| Servicio/volumen | `compose.yaml`, Dockerfile si aplica, arquitectura y operación. |

Antes de crear un módulo nuevo, identifica quién es dueño de los datos y qué dirección de dependencia necesita. La [arquitectura](ARCHITECTURE.md#reglas-de-dependencia) define esos límites.
