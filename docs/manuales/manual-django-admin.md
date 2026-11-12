# Manual de usuario de Django Admin

Este manual explica cómo consultar y, cuando corresponde, mantener los datos internos desde
Django Admin. Está dirigido a administradores funcionales; no sustituye las guías de despliegue,
respaldo o recuperación.

- [Manual del portal principal](manual-portal-principal.md)
- [Índice de manuales](README.md)
- [Operación y respaldos](../operations/OPERATIONS.md)

> **Precaución:** Django Admin trabaja directamente sobre la base de datos. Un formulario visible
> no implica que sea seguro editarlo. Antes de cambiar catálogos, configuración del pipeline o
> relaciones, confirme el efecto con la persona responsable de la operación.

## Índice

1. [Acceso, navegación y permisos](#acceso-navegación-y-permisos)
2. [Reglas de uso seguro](#reglas-de-uso-seguro)
3. [Cuentas y permisos](#cuentas-y-permisos)
4. [Mercado y dashboard](#mercado-y-dashboard)
5. [Pipeline canónico](#pipeline-canónico)
6. [Reportes históricos de reseñas](#reseñas-heredadas)
7. [Pulso del scheduler](#scraping-heredado)
8. [Notificaciones](#notificaciones)
9. [Flujos frecuentes](#flujos-frecuentes)
10. [Problemas frecuentes](#problemas-frecuentes)

## Acceso, navegación y permisos

### Propósito

Django Admin permite administrar cuentas, catálogos y configuraciones, y consultar registros
técnicos que el portal presenta de forma resumida. No es la pantalla recomendada para ejecutar
manualmente el pipeline: use **Pipeline de mercado** en el portal.

### Acceso

1. Abra `/admin/`, por ejemplo `http://127.0.0.1:8000/admin/` en desarrollo.
2. Ingrese con una cuenta activa que tenga **Es staff** habilitado.
3. La cuenta también necesita permisos de ver, agregar, cambiar o eliminar para cada modelo. Un
   superusuario los posee todos.

Los grupos funcionales **Analista**, **Operador** y **Administrador** asignan permisos de negocio,
pero sólo las cuentas con **Es staff** pueden entrar a Django Admin. Al usar **Ver el sitio** se
abre el portal; una cuenta staff encuentra allí **Volver a administración** en el menú de usuario.

**Captura sugerida:** `[CAPTURA-ADMIN-01: inicio de Django Admin con los bloques de aplicaciones,
sin nombres de usuario, correos ni datos productivos]`.

### Navegación común

- Seleccione una aplicación y luego un modelo para abrir su listado.
- Cuando exista, use la búsqueda y los filtros laterales antes de abrir un registro.
- El enlace de la primera columna abre el detalle. Los controles disponibles dependen de los
  permisos de la cuenta y de las protecciones específicas del modelo.
- **Guardar y continuar editando** conserva el formulario abierto; **Guardar y añadir otro** crea
  un registro adicional. Evite esta última opción en configuraciones únicas.
- Las acciones masivas, incluida la eliminación, afectan todos los elementos seleccionados.
- Cierre la sesión desde el menú de usuario; no deje una sesión administrativa abierta en un
  equipo compartido.

## Reglas de uso seguro

Los avisos usados en este manual significan:

- **Editable:** catálogo o configuración que puede mantenerse si se conoce su contrato.
- **Sólo consulta:** dato producido por una ejecución; cambiarlo rompe la trazabilidad aunque el
  permiso genérico de Django muestre controles de edición.
- **No modificar manualmente:** campo calculado, estado, hash, cursor, marca temporal o relación
  que debe gestionar la aplicación.
- **Precaución al eliminar:** una relación protegida impedirá el borrado; una relación en cascada
  puede borrar detalle e historial dependiente.

Antes de una operación sensible:

1. compruebe que está en el entorno correcto;
2. haga el respaldo indicado en la guía de operaciones;
3. cambie un registro por vez y valide el resultado en el portal;
4. no copie contraseñas, cookies, tokens ni credenciales en campos JSON;
5. no elimine ejecuciones, snapshots, observaciones, artefactos ni incidencias para “limpiar” la
   interfaz.

> **Precaución:** `settings_json`, `content_json`, `retry_policy_json`, `metadata_json`, evidencia y
> payloads son estructuras técnicas. Algunas validan formato y ausencia de secretos, pero una
> edición sintácticamente válida todavía puede alterar el comportamiento o la auditoría.

## Cuentas y permisos

### `accounts.User` — Usuarios

- **Propósito:** cuentas que acceden al portal y, si son staff, al Admin.
- **Campos:** correo electrónico, nombre, apellidos, contraseña cifrada, estado activo, staff,
  superusuario, grupos, permisos individuales, último acceso y fecha de alta.
- **Relaciones:** grupos y permisos; además puede aparecer como creador, actualizador o solicitante
  de presets, configuraciones y ejecuciones.
- **Operaciones:** un administrador autorizado puede crear cuentas, cambiar datos, restablecer la
  contraseña y asignar grupos. Desactive una cuenta en lugar de eliminarla.
- **Restricciones:** el correo es el identificador de acceso. No conceda superusuario para resolver
  una necesidad puntual.
- **Precaución al eliminar:** las relaciones históricas protegidas pueden impedir el borrado. No
  elimine usuarios asociados a auditoría.

### `auth.Group` — Grupos

- **Propósito:** agrupar permisos. La instalación define **Analista**, **Operador** y
  **Administrador**.
- **Campos:** nombre y permisos.
- **Relaciones:** usuarios miembros y permisos de cada modelo.
- **Operaciones:** consulte o asigne usuarios; cambie permisos sólo como decisión de seguridad.
- **No modificar manualmente:** no renombre ni elimine los grupos funcionales sin revisar la
  inicialización y la matriz de permisos. Una cuenta staff sin permisos seguirá entrando al Admin,
  pero no podrá operar modelos.

## Mercado y dashboard

### `market.Provider` — Proveedores/competidores

- **Propósito:** catálogo central de competidores usado por fuentes, planes, reseñas y filtros.
- **Campos:** nombre, código estable, sitio web, activo, notas, orden de ejecución, ámbito
  (`real` o `demo`) y fechas de creación/actualización.
- **Relaciones:** fuentes canónicas y heredadas, planes, reseñas, presets y ejecuciones.
- **Operaciones:** **Editable** al incorporar o pausar un competidor. Mantenga único y estable el
  código; el orden controla la secuencia de ejecución/presentación.
- **Precaución al eliminar:** casi todas las relaciones usan protección. Desactive el proveedor en
  vez de intentar borrarlo. No convierta un proveedor real en demo, o viceversa, cuando ya tiene
  datos.

### `market.Plan` — Planes heredados

- **Propósito:** identidad de planes del flujo histórico, conservada para compatibilidad.
- **Campos:** proveedor, identificador externo, nombre, producto, clave estable, activo y cantidad
  de ejecuciones exitosas en las que no apareció.
- **Relaciones:** proveedor y snapshots heredados.
- **Operaciones:** **Sólo consulta**; el scraping heredado mantiene estos datos.
- **No modificar manualmente:** clave estable, activo y ausencias. Para análisis actual use los
  planes del pipeline canónico.

### `market.PlanSnapshot` — Snapshots de planes heredados

- **Propósito:** observaciones históricas de precio y características del flujo anterior.
- **Campos:** plan, fecha observada, nombre/producto observados, monto, moneda, periodicidad, texto
  de precio, características, datos crudos, hash y ejecución de scraping.
- **Relaciones:** plan y `scraping.ScrapeRun`; puede ser origen o destino de un cambio.
- **Operaciones:** **Sólo consulta**.
- **Precaución al eliminar:** los snapshots y su ejecución están protegidos y forman evidencia
  histórica. No modifique monto, contenido crudo ni hash.

### `market.DataChange` — Cambios detectados heredados

- **Propósito:** registrar altas, retiros y cambios de precio, características o detalles.
- **Campos:** tipo, snapshot anterior, snapshot nuevo, diferencia JSON y fecha.
- **Relaciones:** hasta dos snapshots heredados.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** tipo, referencias y diferencia son resultado de la comparación.

### `market.DashboardPreset` — Vistas guardadas del dashboard

- **Propósito:** definir vistas del dashboard por ámbito, proveedores y, opcionalmente, planes y
  características.
- **Campos:** nombre, slug, descripción, ámbito, estrategias de selección de planes y
  características, activo, indicador de sistema, creador/actualizador y fechas. El formulario
  incluye listas ordenadas de proveedores, planes y definiciones canónicas.
- **Relaciones:** proveedores, planes canónicos, `pipeline.FeatureDefinition` y usuarios de
  auditoría; puede ser predeterminado en la configuración del dashboard.
- **Operaciones:** los presets ordinarios se crean preferentemente desde el portal. En Admin sólo
  aceptan ámbito real; si la selección es explícita, cada plan debe pertenecer a un proveedor del
  preset. Una característica explícita debe ser canónica y estar publicada dentro de los
  proveedores/planes elegidos.
- **Restricciones:** los presets del sistema **Todos** y **Demostración** son de sólo lectura y no
  se pueden eliminar. Los campos de auditoría y ámbito se gestionan de forma protegida.
- **Precaución al eliminar:** revise primero si el preset es el predeterminado. Las relaciones
  internas del preset se eliminan con él, no los proveedores, planes ni características. Si una
  definición queda inactiva, la vista la omite con aviso; si se elimina, su relación se elimina en
  cascada sin recrearla.

### `market.DashboardSettings` — Configuración de la aplicación

- **Propósito:** centralizar nombre, identidad visual, cabecera y vista predeterminada global.
- **Campos:** nombre de aplicación; logotipos principal/compacto y sus textos alternativos;
  favicon; título, imagen y texto alternativo de cabecera; vista predeterminada, auditoría y fechas.
- **Relaciones:** preset real activo y usuario de auditoría.
- **Operaciones:** **Editable** desde Configuración de la aplicación del portal o Admin.
- **Restricciones:** sólo existe un registro y no se puede eliminar. Una imagen exige texto
  alternativo salvo el favicon; la vista predeterminada debe estar activa y ser real. PNG, JPEG,
  WebP y SVG tienen límites de tamaño/dimensiones; el SVG se sanea y no admite contenido activo.
- **Diagnóstico:** si se rechaza una imagen, compruebe MIME/extensión, 512 KiB, dimensiones y texto
  alternativo. Exporte SVG estático sin scripts, eventos, enlaces ni recursos remotos.

Los selectores de relaciones usan representaciones humanas acotadas (por ejemplo, competidor y
clave estable del plan). Si aparece `Model object (id)`, trátelo como una regresión de interfaz; no
edite claves primarias para intentar corregir la etiqueta.

## Pipeline canónico

Esta aplicación contiene la configuración y la evidencia del flujo vigente de extracción,
limpieza, normalización y publicación. Use el portal para solicitar ejecuciones y el Admin para
configuración excepcional o diagnóstico.

### Configuración y programación

#### `pipeline.MarketSource` — Fuentes de mercado

- **Propósito:** fuente canónica de planes, características o reseñas para un proveedor.
- **Campos:** proveedor, código, nombre, tipo de datos, clave del adaptador, URL, plataforma, país,
  orden, requerida, activa, configuración JSON y fechas.
- **Relaciones:** proveedor y ejecuciones de fuente.
- **Operaciones:** **Editable** por un administrador que conozca el adaptador. La URL debe ser
  segura, el país ISO de dos letras y el JSON un objeto sin secretos.
- **Precaución:** desactivar evita nuevas ejecuciones; no borra historial. No cambie código,
  proveedor o tipo de una fuente ya usada: cree otra fuente para conservar trazabilidad.

#### `pipeline.PipelineConfig` — Configuraciones del pipeline

- **Propósito:** identidad estable de una configuración para extracción, limpieza, normalización o
  equivalencia de características.
- **Campos:** código, etapa, descripción y fecha de creación.
- **Relaciones:** versiones de configuración.
- **Operaciones:** **Editable** sólo para crear un catálogo nuevo. No cambie la etapa de uno que ya
  tenga versiones.
- **Precaución al eliminar:** las versiones lo protegen.

#### `pipeline.PipelineConfigVersion` — Versiones de configuración

- **Propósito:** contenido versionado y reproducible de una configuración.
- **Campos:** configuración, versión, versión de esquema, contenido JSON, hash SHA-256, estado,
  creador, creación y publicación.
- **Relaciones:** configuración, usuario y etapas de perfiles.
- **Operaciones:** cree un borrador, valide el JSON y publíquelo. Las reglas de equivalencia se
  validan con su esquema propio.
- **No modificar manualmente:** hash y fecha de publicación. Una versión publicada es inmutable y
  no se puede eliminar desde el Admin; cree una versión nueva.

#### `pipeline.PipelineProfile` — Perfiles

- **Propósito:** seleccionar una versión coherente del conjunto de etapas ejecutables.
- **Campos:** código, nombre, descripción, activo, versión activa y fechas.
- **Relaciones:** versiones, versión activa y trabajos programados.
- **Operaciones:** **Editable** con precaución. La versión activa debe pertenecer al mismo perfil y
  estar publicada.
- **Precaución:** desactivar un perfil afecta ejecuciones manuales y programadas que lo seleccionan.

#### `pipeline.PipelineProfileVersion` — Versiones de perfil

- **Propósito:** composición versionada de un perfil.
- **Campos:** perfil, número de versión, estado, descripción, creador y fechas de creación/
  publicación.
- **Relaciones:** perfil, usuario, etapas y ejecuciones.
- **Operaciones:** cree una nueva versión borrador y agregue sus etapas antes de publicar.
- **Restricciones:** publicada es inmutable y no eliminable desde el Admin. No reutilice un número
  de versión.

#### `pipeline.PipelineProfileStage` — Etapas de una versión

- **Propósito:** enlazar, en orden, cada etapa con una versión de configuración publicada.
- **Campos:** versión de perfil, etapa, versión de configuración y orden.
- **Relaciones:** versión de perfil y configuración.
- **Operaciones:** **Editable** sólo mientras el perfil esté en borrador.
- **Restricciones:** no repita etapa ni orden; la etapa de la configuración debe coincidir. Al
  eliminar una versión borrador se eliminan sus etapas en cascada.

#### `pipeline.ScheduledJob` — Trabajos programados

- **Propósito:** definir cuándo se ejecuta un perfil desde el scheduler independiente.
- **Campos:** código, nombre, perfil, expresión cron, zona horaria, activo, política de concurrencia,
  política de reintentos y fechas de última/próxima ejecución.
- **Relaciones:** perfil y ejecuciones originadas.
- **Operaciones:** **Editable**. Use una expresión cron de cinco componentes y zona IANA válida.
- **No modificar manualmente:** últimas/próximas fechas; las mantiene el scheduler. `skip` omite una
  coincidencia concurrente y `queue` la encola. El JSON de reintento no admite secretos.

### Ejecuciones y diagnóstico

#### `pipeline.PipelineRun` — Ejecuciones del pipeline

- **Propósito:** cabecera auditable de cada solicitud manual, programada, reintento o reproceso.
- **Campos:** UUID, trabajo, versión del perfil, disparador, estado, inicio/fin/publicación,
  solicitante, resumen de error y metadatos.
- **Relaciones:** trabajo, perfil, usuario, ejecuciones por proveedor, artefactos e incidencias.
- **Operaciones:** **Sólo consulta**; el Admin muestra todos sus campos como lectura y no permite
  agregar ni eliminar.
- **Precaución:** una ejecución parcial puede contener resultados válidos por proveedor. Consulte
  sus hijos antes de diagnosticar.

#### `pipeline.ProviderRun` — Ejecuciones por proveedor

- **Propósito:** resultado y publicación de un proveedor dentro de una ejecución.
- **Campos:** ejecución, proveedor, secuencia, estado, fechas, completitud, publicación y error.
- **Relaciones:** ejecución y proveedor; contiene etapas, snapshots, artefactos e incidencias.
- **Operaciones:** **Sólo consulta**.
- **Precaución al eliminar:** depende en cascada de `PipelineRun` y es padre de más evidencia. No
  borre ni edite estados o fechas.

#### `pipeline.StageRun` — Ejecuciones por etapa de datos

- **Propósito:** métricas y errores de planes, características o reseñas para un proveedor.
- **Campos:** ejecución de proveedor, etapa, secuencia, estado, intentos, fechas, filas de entrada,
  salida/rechazadas, error y diagnóstico JSON.
- **Relaciones:** proveedor ejecutado; contiene fuentes, artefactos e incidencias.
- **Operaciones:** **Sólo consulta**.
- **Precaución:** no corrija contadores manualmente; son evidencia del resultado.

#### `pipeline.SourceRun` — Ejecuciones por fuente

- **Propósito:** detalle del adaptador/fuente utilizado dentro de una etapa.
- **Campos:** estado, etapa, fuente, secuencia, intentos, fechas, filas extraídas/limpias/
  normalizadas, hash, error y metadatos.
- **Relaciones:** etapa y fuente; puede originar snapshots, características e incidencias.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** hash, contadores, intentos, errores y metadatos.

#### `pipeline.RunArtifact` — Artefactos

- **Propósito:** inventario de archivos raw, clean, normalizados, reportes, exportaciones o logs.
- **Campos:** ejecución, proveedor/etapa opcionales, tipo, ruta relativa POSIX, hash, tamaño y fecha.
- **Relaciones:** ejecución y, opcionalmente, proveedor y etapa.
- **Operaciones:** **Sólo consulta**. La ruta es relativa y no es un botón de descarga.
- **Precaución al eliminar:** la fila puede caer en cascada con su ejecución, pero borrar la fila no
  es un procedimiento de limpieza de archivos. Siga la política de retención operativa.

#### `pipeline.QualityIssue` — Incidencias de calidad

- **Propósito:** advertencias y errores encontrados durante procesamiento.
- **Campos:** ejecución, proveedor/etapa/fuente opcionales, severidad, código, mensaje, conjunto,
  columna, referencia de fila, valor JSON y fecha.
- **Relaciones:** distintos niveles de la ejecución.
- **Operaciones:** **Sólo consulta**; filtre por severidad y código para diagnosticar.
- **Precaución:** el valor puede contener evidencia pública recolectada. No lo copie fuera del
  entorno ni lo “corrija” en Admin.

### Datos publicados de planes

#### `pipeline.MarketPlan` — Identidad canónica de planes

- **Propósito:** identidad estable de cada plan por proveedor.
- **Campos:** proveedor, clave externa, primera/última observación y activo.
- **Relaciones:** proveedor y snapshots.
- **Operaciones:** **Sólo consulta**; el pipeline mantiene vigencia y fechas.
- **Precaución al eliminar:** los snapshots protegen la identidad. No cambie la clave externa.

#### `pipeline.PlanSnapshot` — Snapshots canónicos de planes

- **Propósito:** versión observada de nombre, producto y promoción de un plan.
- **Campos:** plan, ejecuciones de proveedor/fuente, fecha observada, nombres original/normalizado,
  producto, URL, promoción, oferta activa, metadatos y creación.
- **Relaciones:** plan y ejecución; contiene precios, características fuente y valores.
- **Operaciones:** **Sólo consulta**. Requiere el permiso especial de visualización del snapshot.
- **Precaución al eliminar:** precios y características dependientes usan cascada. No elimine ni
  edite un snapshot publicado.

#### `pipeline.PlanPriceSnapshot` — Precios de un snapshot

- **Propósito:** conservar montos por periodicidad y su procedencia observada o calculada.
- **Campos:** snapshot, periodo, moneda, monto, equivalente mensual, descuento, promocional,
  procedencia y metadatos.
- **Relaciones:** snapshot de plan.
- **Operaciones:** **Sólo consulta**.
- **Precaución:** el monto original y el calculado tienen significados distintos; no complete un
  valor ausente por intuición. Al borrar el snapshot padre, sus precios se eliminan en cascada.

#### `pipeline.PlanFeatureSource` — Características observadas

- **Propósito:** texto de característica tal como llegó desde una fuente antes de equivalencias.
- **Campos:** snapshot, ejecución de fuente, clave de fila, categoría, nombre original/
  normalizado, inclusión, posición y metadatos.
- **Relaciones:** snapshot, fuente ejecutada y enlaces a valores normalizados.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** texto original, normalización e inclusión son evidencia del flujo.

#### `pipeline.FeatureDefinition` — Definiciones de características

- **Propósito:** diccionario de columnas canónicas o específicas de proveedor.
- **Campos:** código, nombre visible, tipo de dato, unidad, categoría, alcance, proveedor, origen,
  activo y fechas.
- **Relaciones:** proveedor opcional y valores de planes.
- **Operaciones:** normalmente **Sólo consulta**; las crea la normalización/configuración.
- **Restricciones:** una definición canónica no lleva proveedor y una de alcance proveedor sí.
  Código, alcance y tipo deben permanecer estables cuando ya hay valores.

#### `pipeline.PlanFeatureValue` — Valores normalizados

- **Propósito:** valor tipado de una característica para un snapshot.
- **Campos:** snapshot, definición, una sola columna de valor (booleano, entero, decimal, texto o
  JSON), disponibilidad, origen, regla, indicador derivado y metadatos.
- **Relaciones:** snapshot, definición y fuentes que justifican el valor.
- **Operaciones:** **Sólo consulta**.
- **Restricciones:** sólo un campo `value_*` puede tener contenido y debe coincidir con el tipo de
  la definición. No sustituya desconocido por cero o falso desde Admin.

#### `pipeline.PlanFeatureValueSource` — Evidencia de valores

- **Propósito:** enlazar un valor normalizado con una o más características observadas.
- **Campos/relaciones:** valor normalizado y característica fuente.
- **Operaciones:** **Sólo consulta**.
- **Precaución al eliminar:** el enlace se elimina con el valor; la fuente está protegida. Alterarlo
  rompe la explicación de la equivalencia.

### Datos publicados de reseñas

#### `pipeline.MarketReview` — Identidad canónica de reseñas

- **Propósito:** identidad estable de una reseña por proveedor, plataforma e ID externo.
- **Campos:** proveedor, plataforma, identificador externo, primera/última observación y activo.
- **Relaciones:** proveedor y snapshots.
- **Operaciones:** **Sólo consulta**; requiere el permiso especial de visualización.
- **Precaución:** identificadores y actividad los mantiene el pipeline. Los snapshots protegen la
  identidad contra borrado.

#### `pipeline.ReviewSnapshot` — Snapshots canónicos de reseñas

- **Propósito:** contenido observado de reseña y respuesta para una ejecución.
- **Campos:** reseña, ejecuciones de proveedor/fuente, país, usuario, estrellas, comentario,
  respuesta y sus fechas, ingestión/actualización, sentimiento por calificación, días de respuesta,
  hash y metadatos.
- **Relaciones:** identidad de reseña y ejecución.
- **Operaciones:** **Sólo consulta**.
- **Precaución:** contiene texto y nombre público de autores. Limite su exposición; no edite
  comentarios, respuestas, fechas, métricas ni hash.

## Reseñas heredadas

Admin conserva visibles estos modelos únicamente para consulta histórica y compatibilidad.
Fuentes, ejecuciones, resultados, solicitudes y agenda antiguas están ocultos y el scheduler no
los procesa. La pantalla funcional **Reseñas**, su resumen y sus exportaciones ya usan
`pipeline.ReviewSnapshot`; no modifique estos registros esperando cambiar el portal.

### `reviews.MarketReview` — Identidad heredada de reseña

- **Propósito:** identidad deduplicada de una reseña dentro de una fuente heredada.
- **Campos:** fuente, ID externo/interno, hash de identidad, primera/última observación, visible y
  fechas.
- **Relaciones:** fuente y observaciones.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** IDs, hash, visibilidad y marcas temporales.

### `reviews.ReviewObservation` — Observaciones heredadas

- **Propósito:** versión del contenido de una reseña y de la respuesta del desarrollador.
- **Campos:** reseña, fechas, autor, estrellas, comentario, aplicación/país/versión, votos útiles,
  respuesta, indicador de respuesta, payload crudo, hash, ejecución y resultado de fuente.
- **Relaciones:** identidad, ejecución, resultado y enriquecimientos.
- **Operaciones:** **Sólo consulta**; se muestra en el detalle de reseña.
- **Precaución:** contiene texto y nombres públicos. No cambie la respuesta ni sus fechas; se
  valida que una respuesta no sea anterior a la reseña.

### `reviews.ReviewEnrichment` — Enriquecimientos

- **Propósito:** categoría y sentimiento derivados para una observación.
- **Campos:** observación, categoría, sentimiento, estado, analizador/versión, fecha, confianza,
  error y creación.
- **Relaciones:** observación.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** resultado, confianza y estado. Un nuevo algoritmo debe usar otra
  versión, no sobrescribir la evidencia anterior.

## Scraping heredado

Fuentes, ejecuciones, resultados, solicitudes y agenda antiguas se conservan en la base por
compatibilidad, pero no están registradas en Admin ni se procesan automáticamente. El único modelo
visible de esta aplicación es el pulso del proceso vigente.

### `scraping.SchedulerHeartbeat` — Pulso del scheduler

- **Propósito:** indicar qué proceso scheduler está vivo y cuándo informó por última vez.
- **Campos:** nombre, ID de proceso, host, último pulso e inicio.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** ningún campo. Si el pulso está atrasado, diagnostique el servicio;
  editar la fecha sólo oculta el problema.

## Notificaciones

### `notifications.NotificationRecipient` — Destinatarios

- **Propósito:** personas que reciben avisos de errores, cambios y recuperación del scraping
  heredado.
- **Campos:** nombre, correo, activo y preferencias para los tres tipos de aviso.
- **Operaciones:** **Editable**. Desactive un destinatario antes de eliminarlo y pruebe el correo
  desde Configuración del portal.
- **Precaución:** el correo es único y es un dato personal. No lo exponga en capturas o reportes.

### `notifications.NotificationOutbox` — Bandeja de salida

- **Propósito:** cola auditable de mensajes pendientes, enviados o fallidos.
- **Campos:** tipo de evento, destinatarios JSON, clave de idempotencia, asunto, contexto, estado,
  intentos, creación, envío y último error.
- **Operaciones:** **Sólo consulta**.
- **No modificar manualmente:** estado, intentos, clave, destinatarios y contexto. Cambiar una fila
  no es un método seguro para reenviar una notificación.

## Flujos frecuentes

### Crear una cuenta de portal

1. Abra **Usuarios** y seleccione **Añadir usuario**.
2. Registre correo y contraseña temporal.
3. Abra la cuenta creada, complete nombre y apellidos, marque **Activo** y asigne el grupo mínimo
   necesario.
4. Active **Es staff** sólo si necesita Django Admin.
5. Guarde y pida al usuario cambiar su contraseña desde `/accounts/password_change/`.

### Conceder acceso administrativo limitado

1. Asigne el grupo funcional correspondiente.
2. Active **Es staff**.
3. No active superusuario.
4. Inicie una sesión de prueba con esa cuenta y confirme que sólo aparecen los modelos esperados.

### Incorporar una fuente canónica

1. Confirme que el proveedor real existe y está activo.
2. Cree `pipeline.MarketSource` con código nuevo, tipo correcto, adaptador registrado y URL segura.
3. Guarde configuración adicional como objeto JSON sin credenciales.
4. Ejecute manualmente el pipeline desde el portal y revise ejecución, etapas, fuentes e
   incidencias antes de confiar en la agenda.

### Publicar configuración sin perder trazabilidad

1. Cree una nueva `PipelineConfigVersion` en estado borrador.
2. Valide su contenido y publíquela; no edite una versión publicada.
3. Cree una nueva `PipelineProfileVersion`, agregue las etapas con configuraciones publicadas y
   luego publíquela.
4. Selecciónela como versión activa del perfil.
5. Ejecute una prueba manual y revise el resultado antes de modificar trabajos programados.

### Diagnosticar una ejecución

1. Empiece en **Pipeline de mercado** del portal y abra el UUID en Admin sólo si necesita detalle.
2. Revise `PipelineRun.error_summary` y estado.
3. Identifique el `ProviderRun`, luego `StageRun` y `SourceRun` fallido.
4. Revise `QualityIssue` y `RunArtifact`; no modifique sus contenidos.
5. Corrija la fuente o cree una nueva versión de configuración y lance otra ejecución. Conserve la
   fallida como evidencia.

## Problemas frecuentes

### No puedo entrar a `/admin/`

- Verifique que la cuenta esté activa y tenga **Es staff**.
- Si la contraseña no funciona, use el restablecimiento del portal o solicite a otro administrador
  que defina una contraseña nueva.
- Si entra pero no ve modelos, faltan permisos de modelo o pertenencia al grupo adecuado.

### No aparecen botones para agregar, editar o eliminar

Es el comportamiento esperado cuando falta el permiso correspondiente o el modelo está protegido.
Las ejecuciones `pipeline.PipelineRun` y las versiones publicadas tienen restricciones adicionales.
No intente sortearlas modificando la base de datos.

### El formulario rechaza una URL, JSON, país, zona horaria o cron

Corrija el valor indicado por el mensaje. Las fuentes rechazan destinos inseguros; los códigos de
país requieren dos letras; las zonas usan nombres IANA como `America/Lima`; una expresión cron usa
cinco componentes; los campos JSON indicados deben ser objetos y no pueden guardar secretos.

### No puedo eliminar un registro

Una relación `PROTECT` conserva trazabilidad. Desactive el catálogo cuando exista esa opción. No
elimine los registros que lo referencian para liberar el borrado. Si la eliminación es un requisito
operativo excepcional, haga respaldo y evalúe el impacto con la guía de operaciones.

### Una ejecución permanece pendiente o en curso

No cambie el estado en Admin. Revise el proceso scheduler/worker, el último
`scraping.SchedulerHeartbeat`, los logs y la guía de operaciones. Los leases permiten recuperar
trabajo abandonado de forma controlada.

### “Ver el sitio” me sacó del Admin

No cerró la sesión. En el portal abra el menú de usuario y elija **Volver a administración**; esta
opción aparece únicamente para cuentas staff. También puede volver directamente a `/admin/`.

## Política de capturas de este manual

No se incluyen capturas reales porque el Admin puede mostrar correos, nombres públicos de autores,
comentarios, errores, URLs y datos operativos. Para producir una edición ilustrada, use una base
demo sanitizada, recorte toda cabecera con identidad de sesión y reemplace sólo los marcadores
`[CAPTURA-...]`. Nunca capture datos productivos.
