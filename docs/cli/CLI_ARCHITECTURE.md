# Arquitectura de la CLI de scrapers

## Propósito y límites

`scraper_cli` ejecuta scrapers y exporta datos sin inicializar Django, consultar el ORM ni usar
una base de datos. Su entrada es TOML local y su salida son los contratos versionados descritos
en [CLI_OUTPUT_SCHEMAS.md](CLI_OUTPUT_SCHEMAS.md).

La dirección de dependencias es deliberada:

```text
apps Django ────────> scraping_core <──────── scraper_cli
modelos/ORM/UI                              TOML/CSV/JSON

data_cleaning ──────> data_pipeline <────── data_transformation
              perfiles/detección/políticas/reportes/I/O
```

- `scraping_core`: DTO, conversiones canónicas indispensables, errores, seguridad URL, parsers y adapters de datos puros.
- `apps.*`: wrappers que inyectan settings y conectan el núcleo con modelos, servicios y UI.
- `scraper_cli`: configuración, selección, orquestación, mappers y exportadores.
- `data_pipeline`: perfiles, detección, políticas numéricas, reportes e I/O CSV/JSON.
- `data_cleaning` y `data_transformation`: etapas posteriores independientes y reutilizables.

Ninguno de estos cinco paquetes independientes importa `django`, `apps`, modelos, repositorios ORM,
scheduler o correo. El builder comprueba esta regla mediante AST y ejecuta la copia con una URL
de base deliberadamente inválida.

Los adapters conservan literalmente los valores de presentación y `raw_payload`; campos como
`normalized_name`, `Decimal`, periodicidad, fechas con zona e identificadores siguen siendo
canónicos porque forman parte del contrato interno. `scraper_cli` proyecta esos DTO a columnas y
serializa CSV/JSON sin recortar, cambiar mayúsculas o reescribir textos.

El archivo raw puede pasar por `data_cleaning` y después por `data_transformation`; esas reglas no
se ejecutan implícitamente durante scraping. La separación conserva evidencia original y permite
reprocesar. El esquema clean puede perder columnas totalmente vacías y la salida analítica puede
sumar derivados sin alterar el contrato raw. Consulta [Pipeline de datos](../data/DATA_PIPELINE.md).

## Flujo

```text
config.toml
  -> validación estricta y registro allowlist
  -> PlanSourceDTO / ReviewSourceDTO
  -> adapter secuencial
  -> ScrapedPlanDTO / ScrapedReviewDTO
  -> mapper plans_v2 / plan_features_v1 / reviews_v1
  -> validación exacta de claves
  -> CSV o JSON atómico
```

El código del proveedor configurado se convierte en `competidor_id`; `adapter_key` sólo elige
una implementación. La CLI conserva resultados exitosos si otra fuente falla. `--fail-fast`
detiene el tipo en curso tras el primer fallo. Los logs y el resumen van a stderr.

## Configuración

La referencia campo por campo está en [Configuración TOML](CLI_CONFIG.md).

Python 3.12 permite leer TOML con `tomllib`, sin otra dependencia. Se rechazan claves desconocidas
en tablas estructurales, proveedores duplicados, adapters fuera de los registros y URLs distintas
de HTTP/HTTPS o con credenciales embebidas. El subobjeto `config` es propiedad del adapter.

Los valores operativos son `timeout_seconds`, `max_items`, `country_code`, `user_agent`,
`max_response_bytes` y `allow_private_hosts`. Cada fuente puede definir reintentos; reseñas también
admite retraso y `max_pages`. `--limit`, `--timeout` y `--country` tienen precedencia cuando aplican.

Los secretos no forman parte del modelo actual. Un adapter futuro que los necesite debe aceptar
el nombre de una variable de entorno y validar su presencia sin imprimir el valor.

## Adapters disponibles

| Tipo | Clave | Uso |
|---|---|---|
| planes | `anfibius_plans` | planes editoriales Anfibius descargados con HTTPX (precios vacíos si la fuente no los publica) |
| planes | `example_httpx` | HTML público con el contrato de selectores de ejemplo |
| planes | `example_playwright` | la misma estructura después de renderizar Chromium |
| planes | `idrixcontable_plans` | tarjetas del sistema contable iDrix renderizadas con Chromium |
| planes | `perseo_plans` | tarjetas HTML de Perseo WEB, PC y PRIME |
| planes | `siigo_plans` | productos Siigo desde el JSON `__NEXT_DATA__` de la página |
| planes | `fixture_plans` | pruebas y demostración offline |
| reseñas | `fixture_app_reviews` | tienda de aplicación simulada y paginada |
| reseñas | `fixture_location_reviews` | ubicación simulada y paginada |
| reseñas | `google_maps_reviews` | DOM público renderizado de Google Maps con desplazamiento acotado |

`google_maps_reviews` usa Playwright porque las tarjetas se cargan dinámicamente y conserva los campos adicionales verificables en `raw_payload`. No existe todavía una integración para
Google Play, App Store u otras plataformas no implementadas.

## Seguridad y recursos

La ejecución es secuencial. HTTPX limita conexiones, tamaño y timeout; valida SSRF y redirecciones.
Playwright crea un Chromium por fuente, bloquea imágenes/fuentes/media y siempre cierra página,
contexto y browser. Maps usa eventos reales de rueda, reintentos con contextos nuevos y límites de páginas, desplazamientos y tiempo; una vista pública limitada se reporta como fallo en vez de aceptarse como extracción completa. No se evaden CAPTCHA, autenticación ni medidas anti-bot. El operador debe
respetar robots.txt, términos y límites del sitio.

## Integración web preservada

Los módulos originales bajo `apps.scraping` y `apps.reviews` reexportan los contratos puros o
envuelven adapters para inyectar settings Django. Así la web y la CLI usan un único parser sin que
el núcleo conozca persistencia. Las pruebas de dominio/adapters web sirven como regresión.
