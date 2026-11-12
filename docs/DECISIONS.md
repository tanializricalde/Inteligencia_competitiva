# Decisiones de arquitectura

## ADR-020 — Perfil productivo local HTTP explícito y acotado

- Contexto: probar la imagen y secuencia productivas en una estación sin dominio/certificado exige
  HTTP, pero relajar silenciosamente el preflight no basta —las cookies seguras impiden login— y
  podría convertir una configuración local en una publicación insegura.
- Decisión: añadir `--local-http`/`-LocalHttp` como opt-in para check y apply. El perfil exige clave
  fuerte, hosts/orígenes exclusivamente loopback, redirect/cookies HTTP y SSRF privada desactivada;
  omite Nginx/certificado. Los scripts inyectan en Compose una marca interna que activa esos cambios
  de runtime. Sin el argumento siempre inyectan `false` y los settings productivos fuerzan redirect
  y cookies seguras, independientemente de un `.env` local.
- Alternativas: relajar sólo el check; usar settings de desarrollo y dejar de probar la imagen real;
  exigir certificado autofirmado; confiar en que el operador no exponga el puerto.
- Consecuencias: el ensayo permite login por HTTP y conserva build, migración, scheduler, volúmenes
  y readiness productivos. No valida TLS/proxy y nunca habilita LAN: Compose continúa ligado a
  `127.0.0.1`. El preflight público permanece estricto por defecto.

## ADR-019 — Runtime productivo Windows con proxy TLS externo

- Contexto: el runtime ya se construye como contenedores Linux reproducibles y Docker Desktop
  ejecuta Compose en Windows, pero el aplicador y la documentación sólo permitían desplegar desde
  Linux. Nginx/Certbot, sus rutas y su operación siguen siendo específicos de Linux.
- Decisión: mantener Linux + Nginx/Certbot como servidor canónico y soportar en Windows el mismo
  runtime `web` + `scheduler` mediante Docker Desktop y un aplicador PowerShell. El puerto de
  Gunicorn permanece ligado a loopback; una publicación Windows exige un proxy del host que termine
  TLS, preserve `Host` y envíe `X-Forwarded-Proto: https`. El repositorio valida la aplicación y
  Compose, no administra el ciclo de vida de ese proxy ni de Docker Desktop.
- Alternativas: seguir limitando Windows a desarrollo; exponer Gunicorn directamente; mantener una
  segunda imagen/runtime nativo; declarar Nginx Windows como equivalente al despliegue Linux.
- Consecuencias: build, backup, migración y readiness tienen secuencia equivalente en ambos
  sistemas. La operación Windows depende de asegurar el arranque automático de Docker Desktop y el
  proxy; Nginx/Certbot y `deploy/nginx*.conf` continúan siendo exclusivos de Linux. Esta decisión
  reemplaza sólo la restricción de host Windows de ADR-018, no su taxonomía documental.

## ADR-018 — Documentación temática y automatización multiplataforma

Estado: vigente, salvo la restricción de host Windows reemplazada por ADR-019.

- Contexto: las guías operativas crecieron en una carpeta plana, mezclan comandos Bash y
  PowerShell y Windows no dispone de un equivalente ejecutable para el Makefile/bootstrap.
- Decisión: conservar en la raíz de `docs/` los archivos canónicos exigidos por el protocolo del
  repositorio (`README`, arquitectura, decisiones, stack, estructura y seguimiento) y agrupar las
  demás guías en `development/`, `operations/`, `cli/`, `data/` y `product/`. Separar los recorridos
  de desarrollo Linux/Windows cuando los comandos difieran. Mantener producción soportada en Linux
  con Docker Compose + Nginx; Windows será estación de desarrollo/administración y podrá reproducir
  el stack con Docker Desktop, pero no se presentará como host productivo soportado. Añadir un task
  runner PowerShell y bootstrap seguro, más validación de enlaces en Python reutilizable por ambos
  sistemas.
- Alternativas: mantener todos los Markdown planos; duplicar cada guía completa por sistema;
  declarar Nginx/systemd nativos en Windows sin una topología probada.
- Consecuencias: navegación y ownership más claros, comandos Windows verificables y enlaces/builder
  actualizados; los movimientos son incompatibles para enlaces externos antiguos, por lo que el
  índice raíz queda como entrada estable y `make docs-check` valida las rutas nuevas.

## ADR-001 — Monolito modular Django

- Contexto: producto interno con UI, persistencia y trabajos en segundo plano.
- Decisión: monolito modular con capas dominio/aplicación/infraestructura/presentación dentro de apps Django.
- Alternativas: microservicios; arquitectura Django plana.
- Consecuencias: despliegue simple y límites comprobables sin interfaces artificiales.

## ADR-002 — APScheduler en proceso dedicado

- Contexto: el scraping no puede bloquear HTTP ni duplicarse entre workers.
- Decisión: comando `run_scheduler` separado, una instancia, lock de proceso, leases y heartbeat en base.
- Alternativas: Celery/Redis; scheduler en `AppConfig.ready()`.
- Consecuencias: menos infraestructura; adecuado a baja concurrencia, requiere un único scheduler con SQLite.

## ADR-003 — SQLite portable

- Contexto: base inicial simple y futura migración a PostgreSQL.
- Decisión: ORM Django, transacciones cortas, WAL/foreign keys aislados en configuración y sin SQL SQLite en dominio.
- Alternativas: PostgreSQL desde el inicio.
- Consecuencias: operación sencilla; migrar cuando aumenten escrituras, instancias o volumen.

## ADR-004 — Django Templates y assets locales

- Contexto: UI profesional sin complejidad de SPA.
- Decisión: Templates + Tabler/Bootstrap, HTMX selectivo y Chart.js compilados con Vite.
- Alternativas: React/API; CDN.
- Consecuencias: menor superficie operativa; build frontend reproducible requerido.

## ADR-005 — Características como JSON tipado

- Contexto: proveedores heterogéneos y matriz comparativa.
- Decisión: mapa JSON con `{state, value, original}` por clave canónica; `state` distingue `offered`, `not_offered` y `unknown`.
- Alternativas: EAV/tablas normalizadas; texto libre.
- Consecuencias: MVP flexible y semántica explícita; encapsulación permite migrar a tablas si crecen consultas analíticas.

## ADR-006 — Outbox persistente

- Contexto: correo idempotente, auditable y tolerante a fallos.
- Decisión: registrar notificaciones por evento/clave idempotente y enviarlas desde el proceso scheduler, con cooldown de errores.
- Alternativas: envío directo durante scraping; broker externo.
- Consecuencias: consistencia y reintentos sin infraestructura adicional.


## ADR-007 — Dominio de reseñas separado e identidad de competidor

- Contexto: planes y reseñas comparten operación, pero difieren en identidad, paginación, historial y enriquecimiento. El modelo real es `market.Provider`; su tabla es `market_provider`.
- Decisión: `apps.reviews` mantiene fuentes, identidades, observaciones, enriquecimientos y ejecuciones propios. `ReviewSource.provider.code` se proyecta como `competidor_id`; `adapter_key` sólo resuelve una implementación registrada y reutilizable. `Provider.code` se trata como identificador estable: renombrar la etiqueta visible usa `Provider.name`; cambiar `code` requiere migración explícita de identidad externa.
- Alternativas: reutilizar tablas de planes; usar `adapter_key` como competidor; guardar el código duplicado en cada observación.
- Consecuencias: el pipeline es comprensible e independiente; un competidor admite varias fuentes y varios competidores comparten adapter. Las consultas cruzan FK para exportar el código vigente y evitan duplicación.

## ADR-008 — Observaciones y enriquecimiento diferido de reseñas

- Contexto: likes y respuestas cambian, mientras categoría y sentimiento son derivados reprocesables.
- Decisión: identidad estable + observaciones por hash versionado + enriquecimientos por estrategia/versión. El scraper sólo recolecta hechos; el scheduler procesa pendientes aparte.
- Alternativas: sobrescribir una fila; analizar dentro del scraper.
- Consecuencias: trazabilidad, idempotencia y reproceso sin alterar el dato público original, a costa de más tablas y consultas de última observación.

## ADR-009 — Núcleo de scraping y CLI distribuible sin Django

- Contexto: los mismos parsers deben ejecutarse fuera de la aplicación web, sin compartir el proyecto ni acceder a su base de datos.
- Decisión: mover contratos, adquisición pura y conversiones canónicas indispensables a `scraping_core`; hacer que `apps.*` dependa de ese núcleo y que `scraper_cli` lo orqueste desde TOML sin limpiar nuevamente los datos. Los contratos externos son `plans_v2`, `plan_features_v1` y `reviews_v1`. La distribución se construye por allowlist y se valida de forma aislada.
- Alternativas: arrancar Django en la CLI; duplicar parsers; copiar todo el repositorio y eliminar archivos; reescribir imports durante el build.
- Consecuencias: una sola implementación de extracción sirve a web y CLI, y la ausencia de ORM es verificable. La configuración local duplica deliberadamente la definición operativa de proveedores, y cada adapter nuevo debe mantenerse puro y registrarse explícitamente.

## ADR-010 — Pipeline tabular posterior al scraping

- Contexto: los scrapers deben conservar valores observados, pero el análisis necesita limpieza y tipos canónicos reproducibles para tres esquemas públicos.
- Decisión: crear `data_cleaning` y `data_transformation` como etapas independientes, con `data_pipeline` como paquete común mínimo para perfiles, detección e I/O. Las tres operan sobre `pandas.DataFrame`, archivos CSV o arreglos JSON y no importan Django ni acceden a red o base de datos.
- Alternativas: incorporar reglas a los scrapers; hacer que transformación dependa de limpieza; duplicar detección e I/O en ambas CLI.
- Consecuencias: el dato raw permanece auditable y cada etapa se puede ejecutar o probar por separado. Se añade pandas al runtime y el formato final descarta columnas adicionales sólo con una incidencia explícita.

## ADR-011 — Consolidación por tipo en los límites de la CLI

- Contexto: una extracción puede producir varios archivos y carpetas con reseñas, planes y características, pero las APIs de limpieza y transformación operan correctamente sobre un `DataFrame` y un tipo explícito.
- Decisión: mantener las APIs tabulares sin cambios y resolver descubrimiento recursivo, detección por archivo, agrupación y destinos múltiples en `data_pipeline.cli`. Cada grupo se concatena en orden determinista antes de ejecutar una sola vez la etapa correspondiente; `--type` filtra únicamente archivos cuyo tipo se pudo deducir.
- Alternativas: exigir un bucle externo por archivo; aceptar listas en las APIs de dominio; mezclar tipos en una salida; confiar en `--type` sin comprobar cada entrada.
- Consecuencias: se obtiene un archivo consolidado por tipo y los duplicados entre archivos pueden tratarse conjuntamente. El modo lote carga los archivos completos en memoria, omite entradas indeducibles con advertencia salvo en `--strict` y exige `--output-dir` cuando la detección es automática.

## ADR-012 — Salida analítica aditiva y reporte lateral

- Contexto: la propuesta aprobada exige eliminar columnas completamente vacías, conservar hechos originales, auditar tratamientos numéricos y crear sentimiento por estrellas, comparaciones de precios y una vista ancha sin contaminar los contratos raw.
- Decisión: mantener `reviews_v1`, `plans_v2` y `plan_features_v1` como contratos de extracción; permitir un esquema clean dinámico; hacer que transformación conserve las columnas raw presentes y agregue derivados con nombres distintos. Las políticas numéricas se registran por perfil/campo y `QualityReport` es una salida lateral serializable mediante `--report`. La tabla larga de características es canónica y `--wide-output` publica una vista derivada con nulos ante colisiones.
- Alternativas: conservar columnas completamente nulas; rellenar precios o ausencia con cero; sobrescribir texto/importes originales; versionar un nuevo esquema raw; almacenar estados de ausencia dentro del dataset.
- Consecuencias: raw permanece estable y auditable, clean puede variar según contenido y la salida analítica es aditiva. Los consumidores que exigían exactamente el esquema raw deben seguir leyendo el archivo del scraper o seleccionar sus columnas; los nuevos derivados y advertencias quedan trazables sin dos motores de procesamiento.

## ADR-013 — Equivalencias declarativas en el único aplanado de características

- Contexto: 113 textos normalizados producen columnas distintas aunque varios describen usuarios, nómina o módulos equivalentes; las reglas varían por competidor y deben ser auditables.
- Decisión: mantener la tabla larga como canónica y hacer opt-in el aplanado configurado mediante JSON v1 validado. `data_transformation.feature_rules` separa columnas/reductores, reglas `equals`/regex y derivados cerrados; conserva el fallback dinámico y genera un reporte lateral. Sin configuración se selecciona el pivote histórico en el mismo punto, no un segundo comando o pipeline.
- Alternativas: codificar regex por provider; fuzzy matching; plantillas o expresiones evaluables; sustituir definitivamente las columnas dinámicas; modificar el scraper.
- Consecuencias: las equivalencias son reproducibles, versionables y seguras, y una regla puede emitir varios aportes. El archivo debe mantenerse junto con su schema; las colisiones y conflictos fatales impiden publicar, mientras el volumen sigue limitado a procesamiento pandas en memoria.

## ADR-014 — Persistencia operacional normalizada y transición aditiva

- Contexto: los snapshots originales guardan características como JSON y planes/reseñas usan ejecuciones separadas; se necesita trazabilidad por etapa, fuente y configuración sin migrar datos existentes.
- Decisión: añadir `apps.pipeline` como fuente operativa nueva, reutilizando sólo `market.Provider`. Identidades, snapshots, precios, evidencias y valores tipados se normalizan; las tablas legadas permanecen temporalmente para compatibilidad de la UI, pero los casos de uso nuevos no dependen de ellas. ADR-005 queda limitado al flujo legado.
- Alternativas: reescribir migraciones iniciales y romper consumidores; ampliar indefinidamente los JSON; migrar datos que el usuario declaró descartables.
- Consecuencias: SQLite se crea desde cero de forma reproducible y la transición es revisable. Existe duplicación temporal de tablas hasta migrar las pantallas legadas, documentada como limitación y no como dos fuentes activas.

## ADR-015 — Publicación atómica por proveedor

- Contexto: una falla aislada no debe congelar datos correctos de otros competidores ni reemplazar el último snapshot válido.
- Decisión: `ProviderRun` es la unidad de publicación. Sólo se publica dentro de una transacción cuando todas sus etapas y fuentes requeridas son satisfactorias; las consultas nuevas filtran `published_at` y el último proveedor publicado.
- Alternativas: publicación global; publicar cada fuente inmediatamente; consultar simplemente la ejecución más reciente.
- Consecuencias: se conserva disponibilidad parcial segura entre proveedores y cada publicación es explicable. Comparaciones globales deben mostrar la fecha efectiva de cada proveedor.

## ADR-016 — Scheduler unificado, secuencial y con barreras

- Contexto: actualmente existen cron independientes para planes y reseñas; eso no garantiza planes→características→reseñas ni una versión única de configuración.
- Decisión: un `ScheduledJob` resuelve una versión publicada de perfil, crea `PipelineRun` y recorre etapas, proveedores y fuentes por orden determinista con concurrencia uno. Los cron legados dejan de programar capturas automáticas; las herramientas manuales antiguas permanecen sólo durante la transición.
- Alternativas: conservar dos cron; cola paralela; `asyncio.gather` o pools por proveedor.
- Consecuencias: menor presión sobre sitios/SQLite y estados reanudables claros, a costa de mayor duración total. El proceso scheduler continúa único y las transacciones no abarcan scraping.

## ADR-017 — Dashboard publicado, presets tipados y aislamiento REAL/DEMO

- Contexto: el dashboard principal debe reemplazar datos JavaScript ilustrativos por consultas al
  pipeline publicado, permitir branding/presets y conservar un escenario demostrativo sin
  contaminar mercado, scheduler ni notificaciones reales.
- Decisión: `market.Provider.data_scope` es la raíz tipada `REAL`/`DEMO`; planes, precios,
  características y reseñas del pipeline heredan el ámbito por FK obligatoria. `DashboardSettings`
  es singleton y referencia una imagen del storage y un preset real activo. `DashboardPreset` y
  sus tablas ordenadas relacionan proveedores y `pipeline.MarketPlan`; “Todos” y “DEMO” son vistas
  dinámicas protegidas, sin materializar membresías. La presentación permanece en `apps.market`,
  pero una capa de servicio consulta exclusivamente `apps.pipeline` publicado. Se conserva el
  seguimiento canónico en `docs/` en vez del directorio paralelo sugerido por el prompt.
- Alternativas: tabla variable/valor; guardar Base64; reutilizar tablas legadas; identificar demo
  sólo por prefijo; persistir `features-wide`; crear una aplicación/frontend independiente.
- Consecuencias: las relaciones y permisos son migrables y auditables, el almacenamiento puede
  cambiar sin alterar el dominio y la separación de ámbitos se valida en backend. `market` conoce
  la identidad canónica de planes del pipeline para presets; esta dependencia de transición debe
  desaparecer sólo si la presentación completa migra a otro módulo cohesivo.

### Fórmulas y fuentes de los paneles

- Corte: último `ProviderRun` publicado por proveedor dentro del ámbito del preset; se muestran
  sus fechas efectivas y nunca se combinan ejecuciones fallidas/parciales como estado actual.
- Matriz: valores largos `PlanFeatureValue` canónicos de los planes seleccionados. Compatible =
  aporte positivo en todos los planes con dato; no compatible = exclusión/booleano falso explícito
  en todos; limitado = mezcla de estados; sin datos = ningún aporte concluyente. No se interpreta
  ausencia como falso.
- Evolución: precios `scraped` de ejecuciones publicadas dentro de 3/6/12 meses. Por fecha,
  proveedor y moneda se promedia con `Decimal` el precio mensual o
  `effective_monthly_amount` anual almacenado; no se convierte moneda ni se proyecta.
- Precio/calificación: X es el promedio del precio mensual efectivo vigente de los planes
  seleccionados, separado por moneda; Y es el promedio de estrellas de reseñas clasificables del
  proveedor en el periodo; tamaño es el número de reseñas. Las reseñas no se relacionan con planes,
  por lo que el filtro de planes sólo afecta X y esa independencia se rotula.
- Sentimiento: porcentaje positivo/neutral/negativo sobre reseñas con
  `sentiment_from_rating` informado dentro del periodo; las no clasificadas se muestran como conteo
  aparte y no se convierten en neutrales.
- Planes: último snapshot publicado y sus precios mensuales/anuales observados, por moneda y sin
  fabricar equivalencias. La vista anual sólo usa precios anuales existentes.
- Color: el dashboard construye un único mapa determinista para los códigos estables ordenados. Usa
  primero la paleta categórica Okabe–Ito y, tras un ancla cromática, selecciona cada color mediante
  maximin de distancia perceptual OKLab. Si se agotan los ocho colores, genera candidatos por
  ángulo áureo y aplica el mismo criterio. Así ningún competidor comparte color dentro de la vista,
  se evitan tonos perceptualmente cercanos mientras existan alternativas y cada proveedor conserva
  el mismo color en todos sus paneles. No se persiste en snapshots.

## ADR-021 — Catálogo declarativo y cola manual del pipeline

- Contexto: el TOML ya describía iDrix y todas las fuentes reales activas, pero una base migrada no
  ejecutaba el seed; además, las pantallas heredadas consultaban catálogos distintos y no existía
  una acción web para la secuencia completa.
- Decisión: los recorridos soportados ejecutan `migrate` y luego `seed_market_pipeline`. El seed
  sincroniza idempotentemente `MarketSource` (desde ADR-023 ya no replica catálogos heredados), excluye el provider
  fixture y crea versiones nuevas cuando cambia contenido publicado. La acción web sólo crea un
  `PipelineRun` manual pendiente; el scheduler único lo reclama y ejecuta fuera del proceso HTTP.
- Alternativas: incrustar URLs mutables en una migración de datos; ejecutar scraping en la vista;
  mantener activación manual duplicada; reemplazar o vaciar la base al desplegar.
- Consecuencias: una base nueva y una actualización soportada reciben iDrix y fuentes activas sin
  borrar datos, y las versiones publicadas conservan trazabilidad. `config.example.toml` pasa a formar parte de la imagen de
  runtime; los cambios de activación deben expresarse allí si deben sobrevivir al siguiente seed.

## ADR-022 — Configuración visual única y SVG con defensa en profundidad

- Contexto: el nombre de la aplicación y sus imágenes estaban repartidos entre settings, templates,
  una imagen de dashboard y textos de correo; además, el validador sólo reconocía raster y el
  cambio de preset podía reenviar filtros pertenecientes al ámbito anterior.
- Decisión: evolucionar el singleton tipado `DashboardSettings` como única configuración visual,
  conservar su permiso y datos existentes y exponerlo como **Configuración de la aplicación**. Un
  context processor y callbacks de Unfold proyectan nombre e imágenes en portal, autenticación y
  Admin. Los archivos continúan en storage y se entregan por endpoints controlados. SVG se valida
  como XML sin red ni entidades mediante `lxml`, se reduce a una lista cerrada con `nh3`/Ammonia y
  se vuelve a validar antes de almacenar; no se admiten scripts, eventos, estilos, enlaces ni
  recursos. El cambio de vista crea una URL nueva sin filtros transitorios y el backend normaliza
  parámetros GET contra el preset, ámbito y publicación vigentes, dejando un aviso visible.
- Alternativas: tabla genérica clave/valor; Base64 en la base; servir `MEDIA_URL` directamente;
  sanitizador con expresiones regulares; mantener el error HTTP 400; condiciones especiales para
  “Todos” y “DEMO”.
- Consecuencias: una consulta liviana del singleton alimenta templates y Admin, los SVG admitidos
  son deliberadamente menos expresivos y los medios de marca son públicos por naturaleza pero se
  sirven con MIME, `nosniff`, política de recursos y CSP restrictiva. Los nombres internos del
  modelo/permiso se conservan para no invalidar instalaciones ni grupos existentes.

## ADR-023 — Una sola ingesta automática y conservación reversible del legado

- Contexto: el pipeline canónico ya ejecuta y publica planes, características y reseñas, pero la
  inicialización, el scheduler, el portal y Admin seguían exponiendo en paralelo catálogos y colas de
  `scraping` y `reviews`. Sus tablas también sostienen reportes históricos y migraciones, por lo que no
  existe evidencia suficiente para borrarlas.
- Decisión: `pipeline.MarketSource`, `ProviderRun` y `ScheduledJob` son el único camino de ingesta
  automática. Las pantallas, acciones y registros Admin de captura antigua se ocultan; sus colas dejan
  de ejecutarse y la siembra deja de sincronizarlas. Los modelos, datos, migraciones, comandos
  explícitos y reportes que aún dependen de ellos se conservan hasta tener reemplazo y migración.
- Consecuencia: no hay dos capturas compitiendo por el mismo proveedor y la retirada es reversible,
  pero persiste deuda de esquema. Una eliminación futura exige migrar o retirar primero los reportes
  señalados en `docs/data/LEGACY_MODULE_AUDIT.md` y validar un respaldo real.

## ADR-024 — Snapshot REAL de recuperación acotado para Anfibius

- Contexto: la fuente editorial de planes de Anfibius dejó de publicar la estructura que consumía
  el adapter. El pipeline no debe inventar planes ni publicar una ejecución parcial, pero existe
  una captura CLI normalizada y versionada del 5 de octubre de 2026.
- Decisión: una migración de datos crea una única publicación histórica REAL para `anfibius` desde
  un fixture inmutable empaquetado con la migración. Conserva los 3 planes, 15 filas fuente, 186
  valores normalizados y las métricas de 50 reseñas. No fabrica precios. La fecha publicada es la
  de la observación original, de modo que una publicación posterior siempre prevalece. El fixture
  de reseñas elimina nombres, comentarios, respuestas e identificadores externos originales y usa
  claves locales no vinculables. La reversión elimina sólo el snapshot etiquetado y las identidades
  que la propia migración documentó como nuevas y que continúen sin referencias.
- Alternativas: marcar el provider como DEMO; leer `data/normalized/` durante `migrate`; copiar
  datos personales al historial de migraciones; modificar a mano la SQLite; inventar precios; hacer
  que el adapter devuelva datos obsoletos cuando la página falle.
- Consecuencias: el dashboard recupera una línea base auditable de Anfibius sin depender de red ni
  del volumen `data/`, pero esos datos son históricos y no sustituyen reparar o reemplazar la
  fuente. La migración no desactiva el adapter ni impide ejecuciones futuras.

## ADR-025 — Un solo corte publicado para dashboard, comparación y reseñas

- Contexto: el dashboard ya consumía `apps.pipeline`, pero Comparación y Reseñas seguían leyendo
  modelos heredados. Por ello podían aparecer vacías aunque hubiera planes y reseñas normalizados.
  La matriz además reducía cada característica a un color y descartaba tipo, unidad y valor.
- Decisión: `market.dashboard_service` resuelve preset, ámbito, periodo, proveedores, planes y
  características sobre el último `ProviderRun` publicado. Comparación reutiliza esa selección y
  Reseñas combina la misma selección con un queryset canónico de `ReviewSnapshot`. Los presets
  ordinarios distinguen todas las características de una selección explícita mediante
  `DashboardPresetFeature`; los del sistema no materializan relaciones. El filtro temporal usa
  códigos canónicos en GET, se valida en servidor y no modifica el preset. La matriz formatea cada
  valor según `FeatureDefinition.data_type` y `unit`, sin inferir tipos en templates.
- Alternativas: sincronizar el pipeline hacia tablas heredadas; ocultar Comparación/Reseñas;
  filtrar filas sólo con JavaScript; guardar nombres visibles o copiar todas las características en
  “Todos”/“DEMO”; convertir ausencias en cero o falso.
- Consecuencias: las tres superficies comparten procedencia, publicación y aislamiento
  `REAL`/`DEMO`; URLs manipuladas se normalizan y los faltantes producen estados vacíos. Los modelos
  heredados continúan para historial, pero ya no alimentan estas pantallas ni la exportación de
  reseñas. Una definición inactiva se omite con aviso y su eliminación retira sólo la relación del
  preset.

## ADR-026 — La periodicidad no forma parte de la identidad de un plan Siigo

- Contexto: la fuente Next.js de Siigo publica el mismo producto en grupos mensual (`period=1`) y
  anual (`period=12`). El adapter concatenaba el periodo a la clave externa, creando dos planes con
  igual nombre y características; cada uno tenía sólo uno de los precios y el dashboard mostraba
  alternativamente una fila vacía.
- Decisión: la clave pública del producto es el `plan_id` estable. El adapter agrupa sus variantes
  mensual/anual y emite un solo `ScrapedPlanDTO` con `precio_mensual`, `precio_anual_total` y el
  efectivo anual. Antes de fusionar exige igualdad de nombre, producto, moneda, características y
  URL; conserva ambos objetos originales en `raw_payload` y falla si hay periodos duplicados o
  incompatibles. No se cambia `plans_v2`: la corrección hace que `plan_id` cumpla su semántica.
- Alternativas: ocultar en el template el plan sin precio del periodo activo; consolidar durante la
  limpieza; mantener dos IDs y relacionarlos mediante otra tabla; reescribir snapshots publicados.
- Consecuencias: CLI y futuras publicaciones contienen cuatro planes Siigo en lugar de ocho. Los
  archivos y ejecuciones históricos conservan los IDs `clave:1`/`clave:12`; una nueva ejecución
  completa debe publicarse para que dashboard y comparación usen las identidades corregidas.

## ADR-027 — Evidencia y disponibilidad son conjuntos distintos en la matriz

- Contexto: la salida larga materializa valores `unknown/default` para conservar el esquema
  canónico aun cuando un plan no aporta información. El dashboard usaba la mera existencia de esas
  filas para poblar la matriz, de modo que podía mostrar características «Sin datos» en todos los
  competidores. Algunas de ellas sí tienen evidencia en otros planes o publicaciones y no deben
  borrarse ni reinterpretarse como falsas.
- Decisión: mantener todas las definiciones activas con valores publicados en el conjunto
  seleccionable, pero incluir por defecto sólo las que tengan al menos un `PlanFeatureValue` con
  disponibilidad distinta de `unknown` entre los planes seleccionados. `present`, `excluded` y
  `not_applicable` son evidencia. Una selección temporal o un preset explícito puede mostrar una
  definición íntegramente desconocida. Cada celda reduce todos los planes del competidor: sólo un
  conjunto homogéneo produce Compatible, No compatible, No aplica o Sin datos; toda mezcla es
  Parcial. El resumen booleano tiene orden canónico `Sí · No` y el detalle por plan permanece en
  tooltip y nombre accesible. Una capacidad que deba compararse entre proveedores requiere regla
  explícita; no se promociona un fallback sólo porque su texto normalizado coincida.
- Alternativas: eliminar los defaults durante transformación; tratar `unknown` como `false`;
  ocultar la definición también en el selector; filtrar las filas únicamente en JavaScript.
- Consecuencias: la vista inicial evita ruido sin perder trazabilidad ni capacidad de inspección.
  El filtro y los presets conservan la intención explícita del usuario. Promover una capacidad
  exige una nueva versión de configuración y una publicación nueva; no se requiere migración ni
  reescritura de snapshots históricos.
