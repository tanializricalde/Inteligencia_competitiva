# Manual del portal principal

Este manual describe el portal (denominado **Market Watch** en la configuración inicial) que usan
analistas, operadores y administradores. Un administrador puede cambiar ese nombre globalmente.
Se limita a las funciones disponibles en la aplicación actual. Para tareas de administración
avanzada consulta el [manual de Django Admin](manual-django-admin.md).

> **Capturas pendientes:** no se incrustaron capturas de la base activa porque pueden mostrar
> correos, reseñas y datos operativos. Los marcadores de este documento indican las pantallas que
> conviene capturar posteriormente con una cuenta y un conjunto de datos sanitizados.

## Índice

- [Propósito y acceso](#propósito-y-acceso)
- [Roles y permisos](#roles-y-permisos)
- [Navegación común](#navegación-común)
- [Ingreso, contraseña y cierre de sesión](#ingreso-contraseña-y-cierre-de-sesión)
- [Resumen: dashboard competitivo](#resumen-dashboard-competitivo)
- [Configuración de la aplicación](#configuración-de-la-aplicación)
- [Comparación de planes](#comparación-de-planes)
- [Historial de un plan](#historial-de-un-plan)
- [Reseñas](#reseñas)
- [Detalle de reseña](#detalle-de-reseña)
- [Resumen de reseñas](#resumen-de-reseñas)
- [Pipeline de mercado](#pipeline-de-mercado)
- [Notificaciones](#notificaciones)
- [Flujos frecuentes](#flujos-frecuentes)
- [Solución de problemas](#solución-de-problemas)

## Propósito y acceso

El portal centraliza planes, precios, características y reseñas de competidores. El dashboard
usa exclusivamente publicaciones completas del pipeline: una ejecución pendiente, parcial o
fallida no sustituye la última publicación válida.

Para entrar necesitas:

- una cuenta activa creada por un administrador;
- correo electrónico y contraseña;
- los permisos correspondientes a la pantalla o acción;
- un navegador con JavaScript habilitado para los gráficos y controles adaptables.

La dirección habitual de acceso es `/accounts/login/`. La dirección exacta del servidor depende
del entorno de la organización.

## Roles y permisos

| Rol base | Alcance habitual |
| --- | --- |
| **Analista** | Consulta datos de mercado y reseñas; puede exportar reseñas. |
| **Operador** | Incluye lectura y permite ver y encolar el pipeline canónico. |
| **Administrador** | Recibe todos los permisos de aplicación. El acceso a Django Admin también exige que la cuenta tenga estado de personal. |
| **Superusuario** | Tiene acceso total y se reserva para inicialización o administración excepcional. |

Los botones se ocultan cuando falta un permiso, pero algunas entradas del menú pueden seguir
visibles y responder **403 Prohibido**. Eso no indica una contraseña incorrecta: solicita al
administrador el grupo o permiso apropiado. Los permisos particulares pueden hacer que dos
personas del mismo rol vean opciones distintas.

## Navegación común

El menú lateral contiene **Resumen**, **Comparación**, **Reseñas**, **Pipeline de mercado** y,
según permisos, **Notificaciones** y **Configuración de la aplicación**.

- El botón de menú contrae la barra en escritorio y recuerda la preferencia en ese navegador.
- En pantallas pequeñas, el mismo botón abre el menú como un panel lateral.
- Expandido muestra el logotipo principal y el nombre configurado; contraído usa el logotipo
  compacto o las iniciales. Los nombres largos se ajustan sin ocultarse.
- El botón de tema alterna entre apariencia clara y oscura.
- **Volver a administración** sólo aparece para cuentas de personal (`is_staff`).
- **Salir** cierra la sesión mediante una acción protegida; no basta con visitar una URL GET.

> **Captura sugerida:** `[CAPTURA-PORTAL-01: layout general con menú expandido, selector de tema
> y cuenta sanitizada]`.

## Ingreso, contraseña y cierre de sesión

### Ingresar

1. **Nombre de la pantalla.** Bienvenido.
2. **Propósito.** Autenticar al usuario con su correo corporativo.
3. **Cómo acceder.** Abre `/accounts/login/`; una página protegida también redirige aquí.
4. **Elementos disponibles.** **Correo electrónico**, **Contraseña**, **Ingresar**, cambio de
   tema y el enlace **¿Olvidaste tu contraseña?**.
5. **Acciones y flujos.** Escribe ambas credenciales y pulsa **Ingresar**. Si venías de una página
   protegida, el portal intenta volver a ella.
6. **Permisos.** La cuenta debe estar activa; todavía no se requiere un permiso funcional.
7. **Consideraciones.** El identificador es el correo, no un nombre de usuario. Los errores del
   formulario no revelan si una cuenta concreta existe.

### Recuperar acceso

1. **Nombre de la pantalla.** Recuperar acceso.
2. **Propósito.** Solicitar por correo un enlace de restablecimiento.
3. **Cómo acceder.** Desde **¿Olvidaste tu contraseña?** o `/accounts/password/reset/`.
4. **Elementos disponibles.** Campo de correo y botón **Enviar**.
5. **Acciones y flujos.** Envía el formulario, revisa el mensaje y abre el enlace; en **Define
   una contraseña**, escribe y confirma la nueva clave. Al terminar, pulsa **Ingresar**.
6. **Permisos.** No requiere una sesión iniciada.
7. **Consideraciones.** Siempre se muestra “Si existe una cuenta, recibirás instrucciones”. El
   correo sólo llegará si SMTP está configurado. Un enlace expirado o ya usado muestra **El enlace
   no es válido o expiró**; solicita otro.

### Cambiar la contraseña con sesión iniciada

1. **Nombre de la pantalla.** Cambiar contraseña.
2. **Propósito.** Sustituir la clave conociendo la actual.
3. **Cómo acceder.** Abre directamente `/accounts/password/change/`; actualmente no hay enlace
   en el menú principal.
4. **Elementos disponibles.** Contraseña actual, nueva contraseña, confirmación y **Guardar**.
5. **Acciones y flujos.** Completa los tres campos y guarda. La confirmación ofrece **Volver**.
6. **Permisos.** Cualquier usuario autenticado.
7. **Consideraciones.** Se aplican las validaciones de contraseña configuradas por Django.

Para cerrar sesión, pulsa **Salir** en la barra superior. Usa esta acción especialmente en equipos
compartidos.

## Resumen: dashboard competitivo

1. **Nombre de la pantalla.** Resumen / Dashboard de inteligencia competitiva.
2. **Propósito.** Comparar el último estado publicado de planes, precios, características y
   reseñas.
3. **Cómo acceder.** **Resumen** en el menú o `/`.
4. **Elementos disponibles.** Encabezado y filtros plegables; fechas de corte por proveedor;
   selector **Vista**; **Periodo** de 3, 6 o 12 meses; casillas de **Competidores** y **Planes por
   competidor**; **Aplicar filtros**; acciones de vista según permisos; matriz, tres gráficos y
   tarjetas de planes/precios.
5. **Acciones y flujos.** Para filtrar:
   1. abre **Vista y filtros**;
   2. selecciona vista y periodo; cambiar la vista limpia la selección temporal anterior;
   3. marca competidores y planes disponibles;
   4. pulsa **Aplicar filtros**;
   5. la página se desplaza a los resultados y deja encabezado/filtros contraídos;
   6. junto a **Matriz de funcionalidades**, abre **Filtrar características** para buscar,
      seleccionar todas, limpiar, aplicar o restablecer únicamente las filas de la matriz;
   7. usa **Restablecer la vista** si deseas descartar toda la selección temporal.
6. **Permisos.** Todo usuario autenticado puede consultar. Crear, cambiar o eliminar vistas y
   configurar la aplicación requiere permisos separados de Mercado.
7. **Consideraciones.** Los filtros temporales quedan en la URL y no cambian la vista. Una
   combinación obsoleta o manipulada descarta los valores fuera de alcance, muestra un aviso y
   normaliza la URL; nunca mezcla datos reales y DEMO. Sin publicaciones aparece
   **Sin datos para mostrar**.

### Todos, DEMO y vistas personalizadas

- **Todos** es una vista protegida y dinámica con proveedores `REAL` activos que tengan una
  publicación completa. No puede editarse ni eliminarse.
- **DEMO** contiene datos sintéticos separados. La alerta **Datos demostrativos: no representan el
  mercado real** identifica inequívocamente este ámbito. Tampoco puede editarse ni eliminarse.
- Una vista personalizada siempre usa datos `REAL`. Puede incluir **Todos los planes vigentes** de
  sus proveedores o una **Selección explícita**; las características admiten igualmente todas las
  disponibles o una selección explícita.

Para guardar una vista, aplica primero la selección, abre **Guardar una nueva vista**, completa
nombre, identificador, descripción y estrategia, elige proveedores/planes y pulsa **Guardar
vista**. En modo explícito se exige al menos un plan y cada plan debe pertenecer a un proveedor
seleccionado. En modo todos los vigentes no se permiten planes explícitos. Los identificadores
`all` y `demo` están reservados.

La selección temporal de **Filtrar características** no modifica la vista guardada. Para
persistirla, abre **Guardar una nueva vista** o **Actualizar**, elige **Selección explícita** en
características y marca sus códigos canónicos. Si una característica guardada queda inactiva o ya
no aparece en los planes publicados, se omite y se muestra un aviso; al editar puedes guardar de
nuevo para limpiar la relación. Eliminar una definición no la recrea.

Una vista personalizada muestra **Actualizar “Nombre”** y/o **Eliminar vista** si la cuenta tiene
los permisos correspondientes. Eliminar es definitivo para esa configuración, pero no elimina los
datos de mercado.

### Interpretar los paneles

| Panel | Interpretación correcta |
| --- | --- |
| **Matriz de funcionalidades** | Verde: todos los planes compatibles; amarillo: mezcla parcial; rojo: todos no compatibles de forma explícita; gris: todos no aplican; tramado: todos sin datos. La celda muestra valores distintos con tipo y unidad; `0` no equivale a ausencia. Enfócala o pasa el cursor para consultar plan, producto y valor/estado individual. Los booleanos mixtos se muestran siempre como `Sí · No`. |
| **Evolución de precios** | Historia publicada dentro del periodo. Las monedas permanecen separadas. **Ver datos del gráfico** ofrece alternativa tabular. |
| **Precio mensual frente a puntuación** | Eje X: precio mensual efectivo; eje Y: promedio de estrellas; tamaño: número de reseñas. Las reseñas pertenecen al proveedor, no a un plan concreto. |
| **Sentimiento derivado de estrellas** | Porcentajes positivo, neutral y negativo entre reseñas clasificadas; las no clasificadas se cuentan aparte. |
| **Planes y precios observados** | Cambia entre **Mensual** y **Anual**. Sólo muestra importes realmente disponibles; **Precio no informado** no equivale a cero. |

Las fechas del encabezado pueden diferir entre proveedores porque cada uno conserva su última
publicación válida.

> **Captura sugerida:** `[CAPTURA-PORTAL-02: dashboard DEMO con filtros contraídos, matriz
> completa y leyenda visible]`.

## Configuración de la aplicación

1. **Nombre de la pantalla.** Configuración de la aplicación.
2. **Propósito.** Cambiar la identidad global, la cabecera analítica y la vista inicial.
3. **Cómo acceder.** **Configuración de la aplicación** en el menú; ruta
   `/application/settings/`.
4. **Elementos disponibles.** Nombre de aplicación, logotipos principal y compacto, favicon,
   textos alternativos, título/imagen de cabecera y **Vista predeterminada**;
   botones **Guardar configuración** y **Volver al dashboard**.
5. **Acciones y flujos.** Modifica los campos, selecciona una vista `REAL` activa y guarda.
6. **Permisos.** `market.change_dashboardsettings`.
7. **Consideraciones.** Se aceptan PNG, JPEG, WebP o SVG, máximo 512 KiB y 2400×1200 px. Toda
   imagen salvo el favicon exige texto alternativo. El servidor sanea SVG y elimina scripts,
   eventos y referencias remotas; no use SVG interactivos. Al reemplazar un archivo se elimina el
   anterior no referenciado después de confirmar la transacción. El cambio es global.

## Comparación de planes

1. **Nombre de la pantalla.** Comparación de planes.
2. **Propósito.** Comparar planes, precios y características de la última publicación válida del
   pipeline.
3. **Cómo acceder.** **Comparación** en el menú; `/comparison/`.
4. **Elementos disponibles.** Selectores **Vista**, **Periodo** y **Planes publicados**, botón
   **Comparar** y tabla con precio, fecha, características tipadas y diferencias resaltadas.
5. **Acciones y flujos.** Selecciona uno o varios planes (usa Ctrl/Cmd para selección múltiple) y
   pulsa **Comparar**. Sin selección se toman hasta cuatro planes.
6. **Permisos.** Usuario autenticado.
7. **Consideraciones.** Sólo usa snapshots publicados del ámbito elegido. **Precio sin datos**,
   **Sin datos** y **No aplica** son estados distintos y no equivalen a cero o no compatible. Una
   URL con planes ajenos al preset se normaliza sin producir error 500.

## Historial de un plan

1. **Nombre de la pantalla.** Historial del plan.
2. **Propósito.** Mostrar la evolución de precio y el timeline de cambios de un plan legado.
3. **Cómo acceder.** Ruta directa `/plans/ID/history/`; actualmente no existe un enlace general
   desde el menú.
4. **Elementos disponibles.** Gráfico de precio y timeline con tipo, fecha y diferencia registrada.
5. **Acciones y flujos.** Es una vista de consulta; revisa cronológicamente cada cambio.
6. **Permisos.** Usuario autenticado.
7. **Consideraciones.** **Sin cambios** significa que no hay `DataChange` asociado; no prueba que
   nunca se haya ejecutado scraping.

## Reseñas

1. **Nombre de la pantalla.** Reseñas.
2. **Propósito.** Consultar, filtrar y exportar reseñas de la última publicación válida del
   pipeline.
3. **Cómo acceder.** **Reseñas** en el menú; `/reviews/`.
4. **Elementos disponibles.** **Resumen**; exportación **CSV/JSON**; filtros Vista, Periodo,
   Competidores, Buscar, plataforma, país, estrellas, fechas, respuesta y sentimiento; tabla
   paginada de 50 filas.
5. **Acciones y flujos.** Completa los filtros y pulsa **Filtrar**. Abre el comentario para ver el
   historial. CSV/JSON conservan los filtros vigentes.
6. **Permisos.** Ver exige `reviews.view_marketreview`; exportar requiere
   `reviews.export_reviews`.
7. **Consideraciones.** La respuesta puede ser **Sí**, **No** o **Sin datos**. Una tabla vacía
   muestra **No hay reseñas para los filtros seleccionados**. La paginación y exportación conservan
   los filtros. Los campos que el pipeline no obtuvo quedan vacíos; no se fabrican.

> **Captura sugerida:** `[CAPTURA-PORTAL-03: lista de reseñas con textos, autores y correos
> sustituidos por datos ficticios]`.

## Detalle de reseña

1. **Nombre de la pantalla.** Reseña publicada.
2. **Propósito.** Consultar el snapshot perteneciente a la publicación vigente del proveedor.
3. **Cómo acceder.** Pulsa el comentario en **Reseñas**.
4. **Elementos disponibles.** Proveedor, plataforma o fuente, autor, fecha, estrellas, sentimiento,
   comentario, respuesta y fecha de incorporación al pipeline.
5. **Acciones y flujos.** Consulta la tarjeta y usa **← Volver a reseñas**.
6. **Permisos.** `reviews.view_marketreview` y datos `REAL`.
7. **Consideraciones.** **Usuario anónimo**, **(sin comentario)**, **respuesta sin texto** o
   **Sin clasificar** representan datos no obtenidos. Una URL de un snapshot no vigente devuelve
   una respuesta controlada, no expone historia fuera del corte publicado.

## Resumen de reseñas

1. **Nombre de la pantalla.** Resumen de reseñas.
2. **Propósito.** Resumir volumen, calificación, respuestas y sentimiento derivado.
3. **Cómo acceder.** Botón **Resumen** en Reseñas; `/reviews/summary/`. Existe también una
   variante directa por código de proveedor.
4. **Elementos disponibles.** Total, promedio, porcentaje con respuesta, cantidad sin sentimiento,
   distribución de 1–5 estrellas y promedio/mediana de días de respuesta.
5. **Acciones y flujos.** Es una vista de consulta; aplica filtros desde la URL o abre la variante
   del proveedor cuando corresponda.
6. **Permisos.** `reviews.view_marketreview`.
7. **Consideraciones.** Un guión indica falta de datos calculables. Los tiempos sólo incluyen
   reseñas con fechas suficientes.

## Pipeline de mercado

1. **Nombre de la pantalla.** Pipeline de mercado.
2. **Propósito.** Encolar y seguir el flujo canónico de extracción, limpieza, normalización y
   publicación.
3. **Cómo acceder.** **Pipeline de mercado** en el menú; `/pipeline-runs/`.
4. **Elementos disponibles.** **Ejecutar pipeline completo**; tabla de fuentes con proveedor,
   etapa, adapter y estado; hasta 50 ejecuciones con UUID, perfil/version, origen, estado global,
   estado por proveedor, solicitante, inicio y fin.
5. **Acciones y flujos.** Comprueba que las fuentes requeridas estén activas, pulsa **Ejecutar
   pipeline completo** una sola vez y espera. El scheduler procesa planes, características y
   reseñas en segundo plano. Recarga la pantalla para ver el estado.
6. **Permisos.** Ver exige `pipeline.view_pipelinerun`; el botón exige
   `pipeline.add_pipelinerun`. El grupo Operador recibe ambos.
7. **Consideraciones.** Una segunda solicitud para el mismo perfil activo muestra que ya existe una
   pendiente. **Publicada** es el estado que alimenta el dashboard; **Completa** sin publicación no
   implica que sea visible. Si un competidor falta en **Todos**, confirma aquí que su estado sea
   **Publicada**. Si no hay fuentes, el catálogo inicial no fue cargado. El detalle por etapa está
   disponible en Admin.

> **Captura sugerida:** `[CAPTURA-PORTAL-04: pantalla Pipeline de mercado con fuentes ficticias y
> estados sin mensajes de error sensibles]`.

## Notificaciones

1. **Nombre de la pantalla.** Notificaciones.
2. **Propósito.** Consultar y agregar destinatarios de avisos operativos.
3. **Cómo acceder.** **Notificaciones** en el menú; `/settings/`.
4. **Elementos disponibles.** Lista y formulario con nombre, correo, estado y tipos de aviso;
   botón **Probar correo**.
5. **Acciones y flujos.** Agrega destinatarios con las notificaciones deseadas y pulsa **Probar
   correo** para enviar una prueba a tu propia cuenta.
6. **Permisos.** La pantalla exige `notifications.view_notificationrecipient`; agregar exige
   `notifications.add_notificationrecipient`; probar exige
   `notifications.change_notificationrecipient`.
7. **Consideraciones.** La prueba depende de SMTP externo y muestra sólo el tipo de error, nunca
   credenciales. Los horarios del pipeline se administran mediante `pipeline.ScheduledJob`.

## Flujos frecuentes

### Consultar una comparación competitiva

1. Entra en **Resumen**.
2. Confirma que no estás en **DEMO** si necesitas datos reales.
3. Abre **Vista y filtros**, selecciona periodo, competidores y planes.
4. Pulsa **Aplicar filtros**.
5. Revisa primero las fechas de corte y luego matriz, precios y reseñas.
6. Guarda un preset si tienes permiso y reutilizarás la selección.

### Actualizar datos y comprobar el resultado

1. Abre **Pipeline de mercado**.
2. Verifica que las fuentes relevantes estén **Activas**.
3. Pulsa **Ejecutar pipeline completo**.
4. Espera a que el scheduler cambie **Pendiente** a **En curso** y finalmente a un estado terminal.
5. Si queda **Publicada**, vuelve a **Resumen** y confirma las fechas de corte.
6. Si falla o queda parcial, conserva el UUID y comunícalo al administrador.

### Exportar reseñas filtradas

1. En **Reseñas**, aplica los filtros.
2. Revisa que la tabla represente el conjunto deseado.
3. Pulsa **CSV** o **JSON**.
4. Protege el archivo: puede contener texto y nombres públicos de autores.

## Solución de problemas

| Situación | Qué comprobar | Acción recomendada |
| --- | --- | --- |
| No puedo ingresar | Correo, contraseña y estado de la cuenta. | Usa recuperación; si no llega correo, contacta al administrador. |
| Veo 403 Prohibido | Falta un permiso aunque el enlace sea visible. | Solicita el rol o permiso; no repitas la acción. |
| Dashboard sin datos | Vista, filtros, ámbito, fuentes y publicaciones. | Restablece la vista; revisa Pipeline de mercado. |
| Un filtro de la URL ya no es válido | Aviso de valor descartado y URL normalizada. | Revisa la selección visible; el servidor ya excluyó datos ajenos o inactivos. |
| Estoy viendo datos ficticios | Alerta amarilla DEMO y sufijo “· DEMO”. | Selecciona **Todos** o una vista `REAL`. |
| Una imagen de marca es rechazada | Formato, MIME, 512 KiB, dimensiones, texto alternativo o contenido activo SVG. | Corrige/exporta el archivo como PNG, JPEG, WebP o SVG estático; no intentes conservar scripts o recursos remotos. |
| Gráfico sin valores | Puede faltar precio, moneda comparable, fecha o reseña clasificada. | Consulta el estado vacío y no interpretes nulos como cero. |
| Pipeline permanece Pendiente | Scheduler detenido o ocupado. | Espera; si persiste, contacta al administrador con el UUID. |
| Ejecución Fallida/Parcial | Fuente externa, estructura o límite de carga. | Conserva el error y UUID; no edites registros históricos. |
| No aparece Ejecutar/Solicitar/Exportar | Falta permiso o la fuente está inactiva. | Pide revisión de rol y configuración. |
| No llega correo | SMTP o destinatario inactivo. | Usa **Probar correo** si tienes permiso y comunica el resultado. |
| Una reseña no tiene fecha/respuesta | La fuente no proporcionó el dato. | Trátalo como desconocido; no lo completes por suposición. |

Contacta al administrador cuando el problema afecte permisos, cuenta, scheduler, SMTP, fuentes,
URLs, adapters o una ejecución fallida. Incluye pantalla, hora aproximada y UUID/ID, pero nunca
contraseñas, cookies ni archivos con datos personales.
