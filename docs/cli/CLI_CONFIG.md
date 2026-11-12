# Configuración TOML de la CLI

Esta es la referencia del archivo indicado mediante `--config`. La CLI usa TOML, valida el
documento completo antes de iniciar cualquier scraper y rechaza claves desconocidas. Parte de
[config.example.toml](../../config.example.toml), cópialo con otro nombre y valida cada cambio:

```bash
cp config.example.toml config.toml
python -m scraper_cli validate-config --config config.toml
```

En Windows PowerShell usa `Copy-Item config.example.toml config.toml` y
`.\.venv\Scripts\python.exe -m scraper_cli validate-config --config .\config.toml`. Consulta
[Linux y Windows](../development/WINDOWS_LINUX.md) para las convenciones de rutas y continuación de líneas.

La configuración contiene tablas opcionales `[defaults]` y `[output]`, y uno o más bloques
`[[providers]]`. Cada proveedor puede contener cero o más fuentes de planes y de reseñas.

```text
[defaults]
[output]
[[providers]]
  [[providers.plan_sources]]
    [providers.plan_sources.config]
  [[providers.review_sources]]
    [providers.review_sources.config]
```

## Destino predeterminado: `[output]`

| Campo | Tipo | Predeterminado | Propósito |
| --- | --- | --- | --- |
| `directory` | ruta no vacía | directorio actual | Carpeta de los nombres configurados por proveedor y fallback de `all`. |

Puede ser absoluta o relativa. Una ruta relativa se resuelve desde el directorio donde se ejecutó
la CLI, no desde el archivo TOML. La carpeta puede no existir: se crea al exportar. Es un error
claro si la ruta o alguno de sus padres existentes es un archivo.

```toml
[output]
directory = "cli_dist/csv"
```

En Windows se recomienda conservar `/` como en el ejemplo. También son válidos
`directory = 'cli_dist\csv'` o `directory = "cli_dist\\csv"`.

## Valores globales: `[defaults]`

Todos los campos son opcionales.

| Campo | Tipo | Predeterminado | Propósito |
| --- | --- | --- | --- |
| `timeout_seconds` | entero mayor que cero | `20` | Timeout por fuente cuando ésta y la CLI no lo sobrescriben. |
| `max_items` | entero mayor que cero | `100` | Máximo de registros por fuente cuando no se pasa `--limit`. |
| `country_code` | cadena ISO-2 | ausente | País usado por reseñas si no existe otro valor más específico. |
| `user_agent` | cadena no vacía | `MarketMonitorCLI/1.0` | User-Agent de los adapters HTTPX y Playwright; conviene añadir contacto. |
| `max_response_bytes` | entero mayor que cero | `5000000` | Tamaño máximo aceptado por el adapter HTTPX de planes. |
| `allow_private_hosts` | booleano | `false` | Permite destinos privados/locales. Déjalo en `false` fuera de pruebas controladas. |

Ejemplo:

```toml
[defaults]
timeout_seconds = 20
max_items = 100
country_code = "PE"
user_agent = "MarketMonitorCLI/1.0 (+operaciones@example.com)"
max_response_bytes = 5000000
allow_private_hosts = false
```

## Proveedores: `[[providers]]`

Debe existir al menos uno. `code` no puede repetirse.

| Campo | Tipo | Obligatorio | Propósito |
| --- | --- | --- | --- |
| `code` | cadena no vacía | sí | Identificador estable exportado como `competidor_id` y usado por `--provider`. |
| `name` | cadena no vacía | sí | Nombre visible exportado como `competidor_nombre` en planes. |
| `plans_filename` | nombre de archivo | no | Salida de `plans` cuando se selecciona sólo este proveedor y no se pasa `--output`. |
| `reviews_filename` | nombre de archivo | no | Salida de `reviews` bajo las mismas condiciones. |
| `plan_sources` | lista de tablas | no | Fuentes de planes del proveedor. |
| `review_sources` | lista de tablas | no | Fuentes de reseñas del proveedor. |

Los dos nombres deben ser nombres simples, sin `/`, `\`, `..` ni directorios. Su extensión debe
coincidir con `--format`: `.csv` para el formato predeterminado o `.json` para JSON.

`adapter_key` no es el identificador del competidor: sólo selecciona una implementación registrada.
Consulta las claves disponibles en la instalación con:

```bash
python -m scraper_cli list-adapters
```

## Fuentes de planes: `[[providers.plan_sources]]`

| Campo | Tipo | Obligatorio | Predeterminado / regla |
| --- | --- | --- | --- |
| `name` | cadena no vacía | sí | Nombre operativo usado por `--source` y en errores. |
| `adapter_key` | cadena | sí | `anfibius_plans`, `example_httpx`, `example_playwright`, `idrixcontable_plans`, `perseo_plans`, `siigo_plans` o `fixture_plans`. |
| `url` | cadena HTTP/HTTPS sin credenciales | sí | Se valida también contra destinos privados al ejecutar adapters de red. |
| `enabled` | booleano | no | `true`; las fuentes deshabilitadas no se seleccionan ni se ejecutan. |
| `timeout_seconds` | entero mayor que cero | no | Hereda `[defaults].timeout_seconds`. |
| `retry_limit` | entero no negativo | no | `2`; `anfibius_plans`, `example_httpx`, `perseo_plans` y `siigo_plans` lo aplican. Los adapters Playwright gestionan su espera en Chromium. |
| `config` | tabla | no | Opciones estrictas propias del adapter. |

Los adapters `anfibius_plans`, `example_httpx`, `example_playwright`, `idrixcontable_plans`, `perseo_plans` y `siigo_plans` no admiten actualmente campos dentro de
`config`. Los dos adapters `example_*` esperan el contrato HTML documentado para el provider de ejemplo; Playwright se
usa cuando la página debe renderizar JavaScript.
`anfibius_plans` descarga con HTTPX la sección editorial de planes (Básico, Estándar y Premium / Corporativo); como la fuente no publica importes, exporta precio vacío y periodicidad desconocida. `perseo_plans` descarga con HTTPX las columnas Divi de Perseo WEB, PC y PRIME y consolida precios mensual, anual y de pago único cuando coexisten.

`siigo_plans` descarga HTML con HTTPX y extrae `props.pageProps.products.products` del script JSON `__NEXT_DATA__`; no necesita ejecutar JavaScript. Su allowlist `included_products`, definida en el adapter, exporta actualmente solo `accounting-suscripcion`; para ampliar el alcance se agregan claves explícitas a esa lista y se actualizan sus pruebas.

`idrixcontable_plans` renderiza la página con Playwright y espera el panel cuyo `id` termina en
`-content-contable`; el prefijo Radix es dinámico y no se configura. Solo procesa las cuatro tarjetas
del sistema contable y excluye el tab ERP. Exporta los importes publicados como mensuales sin IVA;
el costo único de implementación se conserva en `raw_payload` hasta que el esquema tenga un campo
dedicado.

Ejemplo iDrix Contable:

```toml
[[providers]]
code = "idrixcontable"
name = "iDrix Contable"

  [[providers.plan_sources]]
  name = "Planes del sistema contable iDrix"
  adapter_key = "idrixcontable_plans"
  url = "https://idrixcontable.com/planes"
  timeout_seconds = 30
```

Ejemplo HTTPX:

```toml
[[providers]]
code = "competidor_a"
name = "Competidor A"

  [[providers.plan_sources]]
  name = "Planes públicos"
  adapter_key = "example_httpx"
  url = "https://example.com/plans"
  enabled = true
  timeout_seconds = 15
  retry_limit = 1
```

### Configuración de `fixture_plans`

Es un adapter offline para demostración y pruebas. Su tabla `config` admite únicamente:

| Campo | Tipo | Obligatorio | Regla |
| --- | --- | --- | --- |
| `fixture_plans` | lista de objetos | sí | Planes que devolverá el adapter. |
| `allow_empty` | booleano | no | Si es `true`, una lista vacía no se considera sospechosa. |
| `simulate_error` | cadena | no | `timeout` o `structure` fuerzan el error correspondiente. |

Cada elemento de `fixture_plans` admite los siguientes datos del DTO canónico:

| Campo | Tipo | Obligatorio | Predeterminado / regla |
| --- | --- | --- | --- |
| `name` | cadena no vacía | sí | Nombre del plan. |
| `external_id` | cadena | no | Si falta, el exportador crea un ID determinista. |
| `product` | cadena no vacía | no | Producto o familia a la que pertenece el plan; se exporta como `producto`. |
| `price` | número o cadena decimal | no | Precio canónico. |
| `currency` | cadena | no | `USD`; se conserva como la entrega la fuente. |
| `periodicity` | cadena | no | `unknown`; valores: `monthly`, `yearly`, `one_time`, `custom`, `unknown`. |
| `price_text` | cadena | no | Usa `price` si se omite. |
| `discount_percentage` | número o cadena decimal | no | Porcentaje de descuento. |
| `price_after_discount` | número o cadena decimal | no | Precio después del descuento. |
| `monthly_price` | número o cadena decimal | no | Precio mensual explícito. |
| `annual_total_price` | número o cadena decimal | no | Total anual explícito. |
| `effective_monthly_price` | número o cadena decimal | no | Precio mensual efectivo explícito. |
| `is_offer_active` | booleano | no | Estado de la oferta. |
| `promotion_text` | cadena | no | Texto promocional público. |
| `features` | tabla | no | Mapa de características; por defecto vacío. |

Una característica usa una clave canónica y puede contener `state` (`offered`, `not_offered` o
`unknown`), `value`, `original`, `category` y `additional_cost`.

```toml
  [[providers.plan_sources]]
  name = "Fixture de planes"
  adapter_key = "fixture_plans"
  url = "https://fixture.invalid/plans"

    [providers.plan_sources.config]
    allow_empty = false
    fixture_plans = [
      { external_id = "pro", product = "facturacion", name = "Plan Pro", currency = "PEN", periodicity = "monthly", monthly_price = "49.90", discount_percentage = "10", price_after_discount = "44.91", is_offer_active = true, features = { soporte = { state = "offered", original = "Soporte", category = "Atención" } } }
    ]
```

## Fuentes de reseñas: `[[providers.review_sources]]`

| Campo | Tipo | Obligatorio | Predeterminado / regla |
| --- | --- | --- | --- |
| `name` | cadena no vacía | sí | Nombre operativo usado por `--source` y en errores. |
| `adapter_key` | cadena | sí | `fixture_app_reviews`, `fixture_location_reviews` o `google_maps_reviews`. |
| `url` | cadena HTTP/HTTPS sin credenciales | sí | URL de procedencia exportable, incluso para fixtures. |
| `platform` | cadena no vacía | sí | Plataforma exportada, por ejemplo `google_play` o `location`. |
| `app_id` | cadena no vacía | no | Identificador de aplicación usado como fallback en reseñas. |
| `country_code` | cadena ISO-2 | no | Hereda `[defaults].country_code`; `--country` tiene mayor prioridad. |
| `enabled` | booleano | no | `true`; una fuente deshabilitada no se ejecuta. |
| `timeout_seconds` | entero mayor que cero | no | Hereda el timeout global. |
| `retry_limit` | entero no negativo | no | `2`. |
| `request_delay_seconds` | número no negativo | no | `0`; pausa entre páginas, no entre registros. |
| `max_pages` | entero mayor que cero | no | `20`; límite defensivo de paginación. |
| `config` | tabla | depende del adapter | Opciones estrictas; Maps dispone de valores predeterminados. |

`google_maps_reviews` renderiza una URL pública de Google Maps con Playwright, desplaza la lista de forma acotada y extrae cada tarjeta por `data-review-id`. La migración de Django crea las fuentes de Anfibius, Perseo y Siigo Contífico deshabilitadas; en el TOML verifica siempre `enabled` antes de ejecutar una fuente.

### Configuración de Google Maps

`google_maps_reviews` admite estas claves opcionales dentro de `config`:

| Campo | Tipo | Predeterminado / regla |
| --- | --- | --- |
| `page_size` | entero 1–1000 | `20`; tarjetas solicitadas por sesión, limitado además por `--limit`/`max_reviews`. |
| `max_scrolls` | entero 1–1000 | `200`; máximo de eventos de rueda por intento. |
| `stable_scroll_attempts` | entero 1–20 | `5`; considera agotada la lista si el conteo no crece. |
| `scroll_pause_ms` | entero 100–10000 | `1200`; espera entre desplazamientos. |
| `scroll_pause_jitter_ms` | entero 0–5000 | `350`; variación aleatoria sumada o restada a la pausa. |
| `scroll_distance_min` | entero 100–5000 | `700`; distancia mínima de un evento de rueda. |
| `scroll_distance_max` | entero 100–5000 | `1400`; distancia máxima; no puede ser menor que el mínimo. |
| `scroll_rest_every` | entero 1–100 | `10`; aplica un descanso adicional cada N desplazamientos. |
| `scroll_rest_ms` | entero 0–30000 | `4000`; duración base del descanso periódico; `0` lo desactiva. |
| `max_load_seconds` | entero 10–3600 | `180`; límite duro de carga por intento. |

La cantidad efectiva queda acotada por `--limit` (o `[defaults].max_items`), `page_size × max_pages` y las reseñas que Maps exponga. Antes del primer scroll, el adapter lee el total visible y reduce el objetivo a ese total: una ficha de una o diez reseñas ya cargadas no espera desplazamientos inútiles. `retry_limit` renueva el contexto ante timeout o falta de avance; cada intento conserva sus límites, por lo que nunca espera indefinidamente. Si una carga posterior se detiene, conserva las tarjetas ya obtenidas, advierte y devuelve código `4`.

Cada lote vuelve a abrir Maps y recorre desde el inicio hasta `offset + page_size`. Por eso una fuente grande debe preferir uno o dos lotes amplios: cuarenta lotes de diez reseñas repiten mucho más trabajo y multiplican la probabilidad de una navegación fallida. La cadencia aleatoria, descansos periódicos, espera creciente y fallback al último elemento visible ayudan a sincronizar el lazy-loading; no evaden autenticación, CAPTCHA ni restricciones de Google.

Los perfiles de `config.example.toml` se dimensionan por el total observado:

| Proveedor | Total esperado | `page_size` | `max_pages` | `timeout_seconds` | `max_load_seconds` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Perseo | 1 | 10 | 2 | 45 | 60 |
| iDrix | 10 | 25 | 2 | 60 | 120 |
| Anfibius | 50 | 100 | 2 | 90 | 300 |
| Siigo | más de 300 | 500 | 2 | 180 | 1200 |

Como línea base del 4 de octubre de 2026, estos perfiles recuperaron 1/1 en Perseo, 50/50 en
Anfibius y 344 reseñas en Siigo; este último backfill tardó 23m 22.98s. Son resultados observados,
no cantidades garantizadas: Maps puede cambiar el total o la representación entregada a otra sesión.

Google puede devolver una “vista limitada” sin contador ni tarjetas incluso para una ficha que un
navegador autenticado sí muestra. El adapter detecta ese estado y devuelve rápidamente
`ReviewTransportError: Google Maps entregó una vista limitada...`; aumentar scrolls o pausas no lo
resuelve. No se deben copiar cookies ni automatizar un inicio de sesión para ocultar esa restricción.

Para una ejecución manual, cambia `enabled = true` sólo en la fuente autorizada y limita el alcance:

```bash
python -m scraper_cli reviews --config config.example.toml --provider anfibius --limit 20 --output resenas-anfibius.csv
```

El adapter exporta ID, autor, estrellas y texto mediante `reviews_v1`. Fecha relativa, URL e ID del autor, avatar, idioma visible, estado de traducción y conteo público del autor se conservan en `raw_payload` para Django. Fecha absoluta, likes, texto original y respuesta quedan en `null` cuando el DOM no los demuestra.

### Configuración de los adapters fixture de reseñas

`fixture_app_reviews` y `fixture_location_reviews` admiten las mismas claves:

| Campo | Tipo | Obligatorio | Predeterminado / regla |
| --- | --- | --- | --- |
| `fixture_reviews` | lista de objetos | sí | Reseñas simuladas. |
| `page_size` | entero entre 1 y 200 | no | `50`. |
| `simulate_transient_failures` | entero no negativo | no | `0`; fallos previos al éxito para probar reintentos. |
| `simulate_http_status` | entero | no | Un valor de 400 a 499 fuerza un fallo no transitorio. |

Cada reseña fixture puede contener:

| Campo | Tipo esperado | Observación |
| --- | --- | --- |
| `external_review_id` | cadena | ID público; si falta se deriva uno estable. |
| `app_id` | cadena | Sólo se conserva en `fixture_app_reviews`; también puede heredarse de la fuente. |
| `country_code` | cadena ISO-2 | Sobrescribe el país de la fuente para esa reseña. |
| `published_at` | cadena ISO-8601 con zona | Fecha del comentario. |
| `author_name` | cadena o nulo | Se conserva sin limpiar ni normalizar. |
| `rating` | entero o nulo | Calificación directa. |
| `review_text` | cadena o nulo | Conserva Unicode y saltos de línea. |
| `app_version` | cadena o nulo | Sólo se conserva en `fixture_app_reviews`. |
| `helpful_votes` | entero o nulo | Cero se conserva y no equivale a ausencia. |
| `developer_response_text` | cadena o nulo | Respuesta pública conservada sin limpiar. |
| `developer_response_at` | cadena ISO-8601 con zona | Fecha de respuesta. |
| `response_known` | booleano o nulo | `true` por defecto; distingue “sin respuesta” de “desconocido”. |

```toml
  [[providers.review_sources]]
  name = "Reseñas offline"
  adapter_key = "fixture_app_reviews"
  url = "https://fixture.invalid/reviews"
  platform = "demo_store"
  app_id = "com.example.app"
  country_code = "PE"
  request_delay_seconds = 0
  max_pages = 10

    [providers.review_sources.config]
    page_size = 50
    fixture_reviews = [
      { external_review_id = "r-1", author_name = "Ana", rating = 5, review_text = "Muy útil", published_at = "2026-01-15T13:00:00Z", helpful_votes = 0, response_known = true }
    ]
```

## Precedencia y selección

- Timeout: `--timeout` → `source.timeout_seconds` → `[defaults].timeout_seconds`.
- Máximo por fuente: `--limit` → `[defaults].max_items`.
- País de reseñas: `--country` → `review_source.country_code` → `defaults.country_code`.
- Archivo: `--output` → `[output].directory` + nombre del proveedor. La opción CLI siempre gana.
- Directorio de `all`: `--output-dir` → `[output].directory`.
- Sin `--output`, `plans`/`reviews` exige seleccionar exactamente un proveedor y que éste tenga el
  nombre correspondiente. Para varios proveedores usa una salida común explícita.
- `--provider` compara exactamente con `providers.code`; puede repetirse.
- `--source` compara exactamente con `source.name`; puede repetirse y aplica dentro de los
  proveedores seleccionados.
- Sin filtros se ejecutan todas las fuentes habilitadas del tipo solicitado, en el orden del TOML.
- Seleccionar una fuente inexistente o deshabilitada produce error de configuración.

## Seguridad, secretos y errores habituales

- No incluyas usuario o contraseña dentro de `url`; el validador los rechaza.
- Conserva `allow_private_hosts = false` salvo una prueba local conscientemente aislada.
- No guardes tokens, cookies ni claves en el TOML. Los adapters actuales no requieren secretos.
- TOML vincula `[providers.plan_sources.config]` o `[providers.review_sources.config]` al bloque de
  fuente declarado inmediatamente antes; respeta la anidación del ejemplo.
- Los nombres de campo son sensibles a mayúsculas y deben coincidir exactamente.
- `validate-config` valida tablas, tipos y configuración general de adapters, pero no hace solicitudes de red ni valida el contenido de cada fila fixture; esas filas se validan al ejecutar el scraper.

Ejemplos de errores que se rechazan antes del scraping: proveedor duplicado, adapter desconocido,
URL `file://`, país que no sea ISO-2, booleano escrito como cadena, timeout cero, tabla `config`
con claves no soportadas o fixture de reseñas sin `fixture_reviews`.

## Política de datos sin limpieza

Los adapters conservan textos públicos, mayúsculas, espacios significativos, Unicode, moneda,
producto y `raw_payload` obtenidos de la fuente. Los campos explícitamente canónicos del contrato
(`normalized_name`, claves de características, `Decimal`, periodicidad, códigos ISO y fechas con
zona) siguen convirtiéndose porque son necesarios para validar, identificar o serializar. CSV cita
comas, comillas y saltos de línea; JSON conserva las cadenas Unicode. La limpieza o enriquecimiento
adicional debe hacerse después de la extracción, no en `scraping_core` ni al exportar.

La única excepción específica de `google_maps_reviews` es que los separadores de línea dentro del
texto visible de una reseña o respuesta se representan como un espacio. Google Maps los entrega
dentro del mismo nodo y no delimitan registros; esta conversión mantiene una reseña por línea física
en CSV sin alterar mayúsculas, puntuación ni el espaciado que ya estaba en una misma línea.
