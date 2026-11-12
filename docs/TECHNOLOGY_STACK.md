# Stack tecnológico

## Criterios de selección

Market Watch es una aplicación interna, de baja concurrencia inicial, que combina interfaz autenticada, persistencia histórica, scraping periódico y correo. El stack prioriza operación sencilla, activos autocontenidos, pruebas offline y una ruta de crecimiento sin introducir servicios distribuidos antes de necesitarlos.

Las versiones de esta página describen las líneas adoptadas, no sustituyen a los manifiestos. Consulta las [fuentes de verdad](README.md#fuentes-de-verdad) para conocer la resolución exacta instalada.

## Lenguaje y framework web

| Tecnología | Versión adoptada | Uso | Justificación |
| --- | --- | --- | --- |
| Python | `>=3.12`; imagen de producción 3.13 | Backend, dominio, scraping, scheduler y pruebas. | Tipado moderno, ecosistema sólido para Django y scraping, y un solo lenguaje para procesos web y de fondo. |
| `argparse`, `tomllib`, `csv`, `json` | biblioteca estándar de Python 3.12 | CLI, configuración y serialización sin framework adicional. | Mantiene pequeña y distribuible la interfaz; TOML permite validación legible sin una dependencia nueva. |
| pandas | `>=2.2,<3` | Limpieza, tipos anulables y transformación tabular posterior al scraping. | Los tres esquemas son tabulares y de volumen pequeño; sus `DataFrame` y dtypes `string`, `Int64`, `Float64` y `boolean` permiten reglas legibles y nulos consistentes sin justificar motores distribuidos. |
| Django | `>=5.2,<5.3` | HTTP, ORM, migraciones, autenticación, formularios, plantillas y admin. | Entrega en un framework cohesivo las necesidades de una aplicación interna y reduce código de integración. El ORM mantiene abierta la migración de SQLite a PostgreSQL. |
| django-environ | `>=0.12,<1` | Lectura y conversión de variables desde `.env`. | Centraliza configuración por entorno y evita incrustar secretos o valores de despliegue en el código. |
| django-unfold | `>=0.65,<1` | Tema y navegación del admin de Django. | Mejora la ergonomía administrativa sin mantener un panel paralelo. La interfaz funcional continúa siendo propia. |
| Gunicorn | `>=23,<24` | Servidor WSGI dentro del contenedor `web`. | Es un servidor de aplicación estable para producción; separa Django del proxy TLS del host. |
| WhiteNoise | `>=6.9,<7` | Archivos estáticos versionados y comprimidos desde Django. | Evita un volumen o servicio adicional para estáticos; el proxy del host sigue encargado de TLS y forwarding. |

El proyecto expone WSGI y ASGI porque Django los genera como puntos de integración. La ejecución productiva vigente usa WSGI con Gunicorn; no hay funcionalidad asíncrona ni WebSockets que requiera un servidor ASGI.

## Persistencia y modelo de datos

| Tecnología | Uso | Justificación y límite |
| --- | --- | --- |
| SQLite | Base de usuarios, configuración, fuentes, ejecuciones, snapshots, cambios y outbox. | Simplifica instalación, backup y operación de una sola instancia. Se activa `foreign_keys`, `busy_timeout=20000` y WAL fuera de pruebas. Debe migrarse a PostgreSQL si crecen las escrituras concurrentes, las réplicas o la disponibilidad requerida. |
| ORM y migraciones de Django | Acceso y evolución del esquema. | Mantienen las reglas de persistencia fuera del dominio puro y permiten cambiar de motor con menor impacto. Las migraciones son parte del código versionado. |
| JSON tipado | Características heterogéneas de planes y payload original. | Conserva flexibilidad entre providers con estados canónicos explícitos. Si predominan consultas analíticas por característica, convendrá normalizar esa parte del esquema. |
| Volúmenes Docker | `sqlite-data` y `evidence-data`. | Separan los datos persistentes de la vida de los contenedores. No equivalen a un backup; la copia verificable se realiza con `manage.py backup_sqlite`. |

## Adquisición y procesamiento

| Tecnología | Versión adoptada | Uso | Justificación |
| --- | --- | --- | --- |
| HTTPX | `>=0.28,<1` | Providers HTTP y clientes comprobables con transportes falsos. | API moderna con timeouts y límites explícitos; facilita pruebas sin red. |
| Beautiful Soup | `>=4.13,<5` | Selección y extracción tolerante desde HTML. | Hace legible la lógica de parsing y soporta HTML imperfecto. |
| lxml | `>=5.3,<7` | Parser de Beautiful Soup, evidencia HTML y estructura XML de SVG. | Ofrece parsing rápido y maduro; para SVG se desactivan red, DTD y entidades antes del saneamiento. |
| nh3 | `>=0.3.6,<1` | Saneamiento por lista permitida de SVG de identidad visual. | Binding mantenido de Ammonia: elimina etiquetas, atributos y URL activas antes de almacenar un archivo administrable. |
| Playwright para Python | `>=1.52,<2` y Chromium | Providers que necesitan ejecutar JavaScript; pruebas de navegador. | Se usa sólo cuando una respuesta HTTP no contiene los datos. El coste de navegador se mantiene fuera del proceso web y se prueba contra fixtures locales. |
| APScheduler | `>=3.11,<4` | Jobs periódicos, cola manual, heartbeat y envío de outbox. | Resuelve la carga actual sin Redis ni un worker distribuido. Corre en un proceso dedicado y exige una sola instancia con SQLite. |
| Tenacity | `>=9,<10` | Dependencia disponible para políticas de reintento. | Fue elegida para reintentos declarativos, pero el provider de ejemplo mantiene hoy un bucle explícito. Debe usarse de forma consistente o retirarse en una limpieza futura; no es una dependencia arquitectónica. |

La distribución CLI independiente instala HTTPX, Beautiful Soup, lxml y Playwright para adquirir,
y pandas para las etapas locales de limpieza/transformación. No incluye Django, drivers de base de
datos, APScheduler ni Gunicorn. Sus contratos y proceso de copiado se documentan en
[Arquitectura CLI](cli/CLI_ARCHITECTURE.md), [Pipeline de datos](data/DATA_PIPELINE.md) y
[Distribución CLI](cli/CLI_DISTRIBUTION.md).

Los adapters implementan un contrato común y devuelven DTO que separan los valores públicos puros
de los pocos campos canónicos requeridos por el contrato. No limpian texto, moneda o producto para
presentación; sólo convierten precios, fechas, periodicidad, códigos ISO, claves e identidades cuando
la validación o el tipo lo exige. El acceso de red, navegador y archivos de evidencia pertenece a
infraestructura; el cálculo de hash y diferencias permanece determinista.

## Interfaz web y activos

| Tecnología | Versión adoptada | Uso | Justificación |
| --- | --- | --- | --- |
| Django Templates | Django 5.2 | Renderizado de páginas y correos. | Evita una API y SPA separadas para una UI interna orientada a formularios y consultas. |
| Tabler | 1.4.0 | Sistema visual, layout y componentes sobre Bootstrap. | Proporciona una interfaz administrativa coherente con CSS local y poco JavaScript propio. |
| Bootstrap | 5.3.7 (transitiva de Tabler) | Grid, formularios, utilidades y variables CSS subyacentes. | Reutiliza un estándar visual conocido; no se declara por separado para evitar dos fuentes de versión. |
| Tabler Icons Webfont | 3.35.0 | Iconografía local. | Evita CDN y conserva consistencia visual/offline. |
| HTMX | 2.0.8 | Base para mejoras HTML progresivas. | Permite interacciones parciales sin adoptar una SPA. Está cargado globalmente, aunque las pantallas actuales no dependen de atributos `hx-*`; debe reservarse para mejoras con beneficio concreto. |
| Chart.js | 4.5.0 | Gráfico del historial de precios. | Resuelve visualización acotada sin introducir un framework de componentes. |
| Sass | 1.93.2 | Estilos fuente en `frontend/src/app.scss`. | Permite personalizar tokens y componentes conservando una única entrada de estilos. |
| Vite | 7.1.7 | Compilación y manifest de JavaScript/CSS. | Build rápido, nombres estables para entradas y assets versionados para producción. |
| Node.js + Corepack + pnpm | Node 20; pnpm 12.6.0 | Instalación reproducible y build frontend. | pnpm reduce duplicación y el lock fija el árbol; Corepack fija el gestor esperado. Node sólo participa en desarrollo y en la etapa de assets de Docker. |

No se cargan recursos de CDN. `src/static/dist/` es artefacto generado por Vite y se incluye en la imagen mediante `collectstatic`; el código fuente editable está en `frontend/src/`.

## Ejecución y despliegue

| Tecnología | Uso | Justificación |
| --- | --- | --- |
| Docker | Imagen multi-stage: Node compila assets y Python ejecuta como usuario no root. | Produce una unidad de despliegue repetible sin llevar toolchain frontend al runtime. |
| Docker Compose | Servicios `web`, `scheduler` y perfil opcional `mailpit`; volúmenes compartidos. | Describe una instalación de un solo host y mantiene web y trabajos de fondo como procesos separados. |
| Nginx | Terminación TLS y proxy a Gunicorn ligado a loopback. | Protege el servidor de aplicación, gestiona certificados, cabeceras y exposición pública. |
| Certbot/ACME | Certificados públicos en la guía de producción. | Automatiza emisión y renovación TLS con una autoridad reconocida. |
| Caddy (opcional en Windows) | Ejemplo de proxy TLS externo para el runtime en Docker Desktop. | Aporta HTTPS automático y forwarding a loopback; no es dependencia de la aplicación ni lo administra Compose. |
| OpenSSL | Certificado temporal y comprobaciones TLS de los scripts de despliegue. | Permite arrancar Nginx de forma controlada antes de emitir el certificado definitivo. |
| SMTP | Transporte de notificaciones y restablecimiento de contraseña. | Protocolo ampliamente soportado; credenciales y remitente se configuran por entorno. |
| Mailpit | SMTP y buzón web bajo el perfil Compose `development`. | Permite inspeccionar correo local sin enviar mensajes reales. No forma parte del perfil productivo. |
| Make y shell POSIX/Bash | Comandos repetibles y validaciones en `Makefile`/`scripts/`. | Ofrecen una interfaz pequeña para desarrollo y despliegue sin añadir otro orquestador. |
| Linux/`fcntl` | Lock de proceso del scheduler. | Evita dos schedulers en un mismo host. Esta implementación concreta no es portable a Windows sin sustituir el mecanismo de lock. |

## Calidad y pruebas

| Tecnología | Versión adoptada | Uso | Justificación |
| --- | --- | --- | --- |
| pytest | `>=8.3,<10` | Runner de toda la suite. | Fixtures y selección por marcadores legibles, con buen aislamiento. |
| pytest-django | `>=4.11,<5` | Base de datos y ciclo Django en pruebas. | Integra pytest con settings, ORM, cliente y transacciones Django. |
| pytest-cov | `>=6,<8` | Medición opcional de cobertura. | Permite detectar áreas sin prueba; la aprobación no descansa únicamente en un porcentaje. |
| Playwright (runtime de navegador) | Navegador real marcado con `playwright`. | Mantiene la suite habitual rápida y permite validar por separado la UI y adapters JS. |
| Ruff | `>=0.11,<1` | Lint y formato de Python. | Sustituye varias herramientas con una ejecución rápida y configuración única. |
| ripgrep (`rg`) | Herramienta del host, sin versión fijada. | Descubrimiento rápido y validación de enlaces Markdown en `make docs-check`. | Mantiene simples los scripts de documentación; debe estar disponible en el entorno de desarrollo. |
| respx | `>=0.22,<1` | Dependencia de desarrollo para simular HTTPX. | Está disponible para pruebas declarativas, aunque hoy se usa principalmente `httpx.MockTransport`. Si continúa sin uso directo, puede retirarse. |
| Fixtures HTML/JS locales | Contratos reproducibles de providers. | Las pruebas no dependen de sitios de terceros, credenciales, latencia ni cambios externos. |

## Por qué no se usan otras piezas todavía

- No hay Celery, Redis ni broker: APScheduler, leases y outbox cubren la carga de una instancia con menos operación.
- No hay PostgreSQL: SQLite es suficiente para la concurrencia actual y el ORM conserva una ruta de migración.
- No hay React/Vue ni API pública: las páginas de servidor cubren el producto con menos superficie de seguridad y build.
- No hay almacenamiento de objetos: la evidencia es local y de volumen acotado; deberá externalizarse si se distribuyen workers o crece su retención.
- No hay CDN: los activos locales permiten operar en redes restringidas y evitan dependencias de terceros durante la carga.

Estas elecciones son límites actuales, no prohibiciones. Los disparadores de evolución se detallan en [Arquitectura](ARCHITECTURE.md#ruta-de-evolución).
