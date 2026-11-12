# Dashboard de inteligencia competitiva

El dashboard autenticado (`/`) compara exclusivamente snapshots canónicos publicados por
`apps.pipeline`. No lee CSV en cada petición, no ejecuta scraping y no mezcla ejecuciones
parciales. La fecha de corte que acompaña a cada proveedor es la publicación que alimenta la
vista.

## Vistas y filtros

La selección inicial se resuelve en este orden:

1. `?preset=slug` válido;
2. preset predeterminado de la configuración global;
3. vista protegida **Todos**.

**Todos** incluye dinámicamente todos los proveedores `REAL` activos que tengan una publicación y
sus planes vigentes. **DEMO** hace lo mismo únicamente en el ámbito `DEMO` y muestra una advertencia
visible. Ninguno de los dos presets se puede editar o eliminar.

El formulario superior permite elegir periodo (3, 6 o 12 meses), proveedores y planes. El control
**Filtrar características**, junto al título de la matriz, permite buscar, seleccionar todas,
limpiar la selección, aplicar o restablecer características. Esos filtros son temporales, quedan
en la URL y no modifican la vista. El servidor limita cantidad y longitud: conserva valores
válidos, descarta los ajenos/inactivos y redirige con aviso a una URL canónica. Por ello una URL
manual obsoleta no mezcla datos `REAL`/`DEMO` ni produce una pantalla de error.

El encabezado y los filtros son desplegables independientes. Al aplicar filtros ambos regresan
contraídos y el navegador salta al inicio de los resultados; pueden volver a abrirse sin recargar.
La matriz de funcionalidades ocupa siempre la fila completa y el resto de paneles cambia a una
columna cuando el espacio disponible es reducido. El botón de menú contrae la barra lateral en
escritorio, recuerda la preferencia en el navegador y la abre como cajón en pantallas pequeñas.
Cuando está expandida muestra juntos el logotipo principal y el nombre global; al contraerse usa
el logotipo compacto o las iniciales. Esta regla también se aplica a nombres largos, raster y SVG.

Los usuarios con `market.add_dashboardpreset` pueden guardar una selección `REAL`. Para actualizar
o eliminar se necesitan, respectivamente, `market.change_dashboardpreset` y
`market.delete_dashboardpreset`. Un preset ordinario puede incluir todos los planes vigentes de
sus proveedores (`all_current`) o una lista explícita; cada plan explícito debe pertenecer a un
proveedor seleccionado. Los presets globales se administran también desde Django Admin.

La selección de características sigue el mismo contrato: `all_current` resuelve dinámicamente las
canónicas disponibles, pero muestra por defecto sólo aquellas con al menos una evidencia
`present`, `excluded` o `not_applicable` entre los planes elegidos. Una característica cuyas celdas
son todas `unknown` permanece en **Filtrar características**, desmarcada, para que el usuario pueda
mostrarla expresamente; también se muestra si forma parte de un preset `explicit`. Este último
guarda únicamente IDs de `FeatureDefinition`. Al cargar se intersecta con las características
activas de la publicación. Una relación temporalmente indisponible produce un aviso no bloqueante;
eliminar la definición elimina sólo esa relación. **Todos** y **DEMO** conservan siempre el modo
dinámico.

Ejemplo “Competidor directo”: abre **Todos**, marca el producto propio y el competidor principal,
elige únicamente los planes básico/intermedio disponibles, aplica los filtros y despliega
**Guardar una nueva vista**. Usa un slug estable como `competidor-directo` y la estrategia
`explicit`. No se codifican IDs: las relaciones se eligen por sus etiquetas y se validan contra la
publicación actual.

## Configuración de la aplicación

Un usuario con `market.change_dashboardsettings` puede abrir **Configuración de la aplicación**
desde el menú o `/application/settings/`, o editar la instancia única en Admin. Puede modificar:

- nombre global de la aplicación;
- logotipo principal y texto alternativo para login, menú y Admin;
- logotipo compacto y texto alternativo para la barra lateral contraída;
- favicon;
- título e imagen de la cabecera analítica con texto alternativo;
- vista `REAL` activa que se abrirá por defecto.

El archivo se guarda mediante el storage de Django bajo `MEDIA_ROOT`; SQLite conserva sólo su
nombre. Se aceptan PNG, JPEG, WebP y SVG de hasta 512 KiB y 2400 × 1200 px. Los SVG se parsean sin
red, DTD ni entidades y se sanean con listas permitidas; scripts, eventos, URL remotas y contenido
activo se eliminan antes de almacenar. Una firma/MIME incompatible, XML inválido o dimensiones
fuera del límite se rechazan. Al reemplazar una imagen, la anterior se elimina después del commit
sólo si ningún campo la referencia. Sin archivo se usa el SVG estático predeterminado; los endpoints
de activos aplican `nosniff`, mismo origen y CSP restrictiva para SVG.

## Significado de los paneles

| Panel | Fuente y cálculo |
| --- | --- |
| Matriz de funcionalidades | Último `ProviderRun` publicado y valores largos canónicos de `PlanFeatureValue`. Cada celda conserva estado, valor tipado y unidad: `0` es un valor, **Sin datos** es ausencia y **No aplica** es un estado explícito distinto. Los textos largos se truncan sólo visualmente; el tooltip y la etiqueta accesible detallan el valor o estado de cada plan. |
| Evolución de precios | Snapshots publicados dentro del periodo. Usa precio mensual observado o `effective_monthly_amount` anual ya persistido cuando no existe mensual. Las monedas se mantienen en series separadas y no hay proyecciones fabricadas. |
| Precio frente a puntuación | X es el promedio del precio mensual efectivo de los planes seleccionados; Y es la media de estrellas del proveedor; el tamaño representa el número de reseñas calificadas. La reseña es independiente del plan, indicado en pantalla. |
| Sentimiento | Porcentaje positivo/neutral/negativo derivado de estrellas sobre reseñas clasificadas del periodo. Las no clasificadas se cuentan aparte y no se tratan como neutrales. |
| Planes | Precios mensuales y anuales realmente observados en la última publicación; no se fabrica una anualidad multiplicando por doce. |

### Diagnóstico de filas «Sin datos»

`unknown` no significa que el plan haya excluido la funcionalidad: indica que el pipeline no tiene
evidencia suficiente para afirmarla o negarla. La transformación puede materializar esos valores
con `origin=default` para mantener el esquema canónico; no debe convertirlos en `false`. Por ello:

- una fila íntegramente desconocida queda oculta en la selección dinámica predeterminada;
- el selector conserva la definición y permite mostrarla deliberadamente;
- `excluded` (**No compatible**) y `not_applicable` (**No aplica**) sí son evidencia y mantienen la
  fila visible aunque no exista ningún `present`.

El estado de cada celda resume todos los planes seleccionados de un competidor:

- **Compatible**: todos tienen evidencia compatible (`present`);
- **No compatible**: todos tienen evidencia explícita `excluded` o booleana falsa;
- **No aplica**: todos están marcados explícitamente `not_applicable`;
- **Sin datos**: todos están `unknown` o no tienen valor publicado;
- **Parcial**: cualquier mezcla de los estados anteriores, por ejemplo un plan compatible y otro
  desconocido o no compatible.

Para booleanos mixtos, el texto visible se normaliza siempre como `Sí · No`, independientemente
del orden de los planes. Los estados desconocidos o no aplicables se consultan en el tooltip. Para
valores numéricos o textuales se conservan los valores distintos en la celda y el tooltip identifica
qué plan aporta cada valor, incluido cero.

Si una característica esperada aparece como «Sin datos» para todos después de seleccionarla,
comprueba que los planes que aportan la evidencia estén marcados, que el proveedor tenga una
publicación vigente y que sus `PlanFeatureValue` no hayan quedado todos como `unknown/default`.
En el dataset de referencia actual, **Centro de costos** se observó únicamente en tres planes
Perseo Prime. La configuración lo promueve ahora a equivalencia canónica explícita; con los doce
planes Perseo de esa muestra, su estado agregado es **Parcial**: tres compatibles y nueve sin datos.
Una publicación creada con la configuración anterior conserva la capacidad bajo un fallback de
proveedor y mostrará la fila canónica como desconocida hasta ejecutar `seed_market_pipeline` y
publicar un reproceso o una ejecución nueva. Los snapshots históricos no se reescriben.

El selector mensual/anual cambia el precio visible del mismo plan; no debe crear ni conservar una
fila vacía por periodicidad. Siigo consolida en el adapter sus variantes `period=1` y `period=12`
bajo la clave externa del producto. Una base que aún muestre pares `clave:1`/`clave:12` conserva
una publicación anterior: ejecuta y publica nuevamente el pipeline de Siigo para sustituirla, sin
editar snapshots históricos.

Los importes se calculan con `Decimal` hasta construir el payload de visualización. Los colores se
asignan de forma determinista sobre códigos estables: primero se usa la paleta accesible Okabe–Ito
y cada elección maximiza en OKLab su distancia mínima respecto de las anteriores. Después de ocho
competidores se generan candidatos adicionales y se conserva la misma regla maximin. Un mapa
compartido evita colores iguales o innecesariamente cercanos y mantiene el tono de cada proveedor
en **Planes y precios observados**, **Precio mensual frente a puntuación** y **Evolución de
precios**. Si faltan datos, cada panel muestra un estado vacío en lugar de sustituirlos por cero.

## Datos DEMO y aislamiento

Las migraciones `market.0006` y `market.0007` crean los presets protegidos y un dataset sintético,
determinista y reversible: cuatro proveedores anónimos, 15 planes, seis publicaciones mensuales,
características y reseñas. Sus códigos reservados empiezan por `demo_` y el perfil sintético queda
inactivo. No se crean fuentes de scraping operativas ni eventos de notificación.

El campo `Provider.data_scope` es la frontera raíz. Formularios, consultas, importación,
publicación, scheduler, comandos legados y exportación de reseñas filtran o rechazan `DEMO`; ocultar
opciones en HTML no es el mecanismo de seguridad. Para añadir datos de demostración, extiende la
migración o crea otra migración acotada y conserva claves naturales reservadas. Nunca cambies un
proveedor real a `DEMO` para probar la interfaz.

Para comprobar el aislamiento después de una migración, abre **Todos** y confirma que ningún código
`demo_` aparece en opciones o payload; luego abre **DEMO** y confirma que no aparece ningún proveedor
real. La comprobación automatizada equivalente es:

```bash
.venv/bin/python -m pytest tests/market/test_dashboard_service.py tests/market/test_dashboard_views.py tests/pipeline/test_orchestrator.py -q
```

## Verificación y diagnóstico

Después de cambios en modelos o consultas:

```bash
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
.venv/bin/python -m pytest tests/market/test_dashboard_models.py tests/market/test_dashboard_service.py tests/market/test_dashboard_views.py -q
```

En PowerShell reemplaza `.venv/bin/python` por `.\.venv\Scripts\python.exe`. Para reconstruir el
frontend usa `make assets` en Linux/macOS o `corepack pnpm --dir frontend install --frozen-lockfile`
y `corepack pnpm --dir frontend build` en Windows. La instalación necesita acceso al registro pnpm
si el almacén local aún no contiene todos los paquetes.

Para investigar un panel vacío o un competidor ausente, abre **Pipeline de mercado** y comprueba el
estado por proveedor. Debe estar activo, pertenecer al ámbito del preset y tener un `ProviderRun`
publicado completo con al menos un plan vigente; luego revisa los snapshots hijos y la fecha de
publicación frente al periodo elegido. Las filas de los módulos heredados no alimentan el dashboard.
No cambies nulos por ceros ni publiques una ejecución fallida para forzar el gráfico.

Anfibius dispone además de un snapshot REAL histórico de recuperación, instalado por la migración
`pipeline.0003_seed_anfibius_recovery_snapshot`. No tiene precios porque el origen no los publicó;
por ello puede aparecer en planes, características y reseñas mientras sus paneles de precio quedan
sin datos. Una ejecución REAL publicada con fecha posterior prevalece sin configuración manual.
