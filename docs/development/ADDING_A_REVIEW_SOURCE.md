# Agregar una fuente de reseñas

Las reseñas usan un pipeline propio bajo `apps.reviews`. No agregues lógica de reseñas a los adapters de planes: sólo comparten scheduler, seguridad URL, outbox y convenciones operativas.

## Identidad y alcance

- `ReviewSource.provider` apunta a `market.Provider`; `provider.code` es el identificador estable del competidor y se exporta como `competidor_id`.
- `ReviewSource.adapter_key` identifica código reutilizable, no una empresa. Dos competidores pueden usar el mismo adapter.
- Un competidor puede tener varias fuentes de la misma o distinta plataforma.
- `source_url` debe ser HTTP/HTTPS y pasa por la protección SSRF existente.

## Reutilizar o crear un adapter

Reutiliza un adapter cuando la plataforma, contrato de respuesta, paginación y autenticación son iguales y sólo cambian el package/place ID, país o URL. Guarda esas diferencias en `external_entity_id`, `country_code` y un `adapter_config` pequeño.

Crea otro adapter cuando cambie el protocolo, el formato o la estrategia de checkpoint. Nunca uses `adapter_key` de la base para importar módulos dinámicamente: registra una factory explícita en `apps/reviews/infrastructure/builtin.py` mediante `register_review_adapter`.

Los adapters `fixture_app_reviews` y `fixture_location_reviews` son demostraciones offline. `google_maps_reviews` procesa el DOM público renderizado de Maps mediante Playwright; debe permanecer deshabilitado hasta confirmar autorización, términos y límites.

## Contrato

Implementa `ReviewScraperAdapter`:

1. `validate_config(source)` valida límites y un esquema específico; falla con un `ReviewScrapeError` controlado.
2. `scrape(source, checkpoint)` devuelve `ReviewScrapeBatch` con DTO, siguiente cursor, `has_more`, metadatos y advertencias.
3. Cada `ScrapedReviewDTO` contiene hechos públicos de la plataforma. No recibe `competidor_id`, sentimiento ni categoría.
4. Fechas deben incluir zona y convertirse a UTC; rating es 1–5; votos útiles no son negativos; país es ISO-2.
5. `None`, cadena vacía, cero y `False` tienen semánticas diferentes y no deben intercambiarse.

El orquestador limita páginas y registros, revisa una ventana reciente y actualiza el checkpoint sólo después de persistir cada lote.

## Términos, robots y método permitido

Antes de cualquier acceso real:

1. revisa los términos vigentes, `robots.txt` y documentación/API oficial de la plataforma;
2. registra la fecha, método permitido, límites y responsable de la revisión;
3. prefiere una API pública/oficial o JSON público embebido en HTML;
4. no evadas CAPTCHA, login, rate limits ni protecciones anti-bot;
5. no uses endpoints privados obtenidos por ingeniería inversa sin autorización;
6. si no existe un método legítimo, conserva el adapter deshabilitado y documenta el bloqueo.

Playwright sólo se justifica si los datos permitidos se generan realmente en el navegador. HTTPX y JSON/HTML público son preferibles.

Para `google_maps_reviews`, la carga dinámica justifica Playwright. El parser prioriza `data-review-id`, atributos ARIA y relaciones dentro de cada tarjeta; no activa traducciones, no evade controles ni convierte fechas relativas en fechas inventadas.

## Configuración y límites

Configura `request_delay_seconds`, timeout, `retry_limit`, `max_pages`, `max_reviews` y `review_window` conservadoramente. En Maps, `page_size`, desplazamientos, pausas con jitter, estabilidad y `max_load_seconds` acotan cada lote. Prefiere un lote que cubra el total esperado para no reabrir y recorrer Maps desde cero muchas veces. Los reintentos renuevan el contexto sólo para timeouts, vista limitada y cargas parciales; un cambio de estructura falla sin un bucle indiscriminado. Tras obtener al menos una tarjeta, un atasco posterior entrega un lote parcial con advertencia y conserva el checkpoint; antes de la primera tarjeta continúa siendo un fallo.

El cursor es JSON validado y opaco para el orquestador, salvo límites comunes. No guardes cookies,
tokens, URLs firmadas ni datos personales fuera del contrato; `raw_payload` debe limitarse a los
campos públicos descritos por el adapter. Filtra secretos y datos fuera de alcance, pero no limpies,
recortes ni normalices los valores públicos permitidos. Las fechas, números y códigos ISO se
convierten únicamente para satisfacer sus tipos de contrato.

## Fixtures y pruebas de contrato

Guarda fixtures mínimos y sanitizados en `tests/fixtures/reviews/` cuando el adapter real exista. Prueba sin Internet:

- parsing con Unicode, comas, comillas, saltos y emojis;
- si el adapter aplana separadores de línea por un contrato de serialización explícito, prueba por
  separado comentario y respuesta y no normalices el resto del texto;
- campos opcionales ausentes y rating sin texto;
- página vacía legítima frente a estructura rota;
- cursor y varias páginas;
- timeout/transitorio con reintento acotado y 4xx sin reintento;
- respuesta agregada después, likes modificados e idempotencia;
- app/package ID para tiendas y ausencia de esos campos para ubicaciones.

Usa `httpx.MockTransport`, respuestas locales o servidor efímero. Una prueba automatizada nunca debe llegar a Internet.

## Alta de una fuente

Declara la fuente bajo `[[providers.review_sources]]` en el TOML autorizado y ejecuta
`seed_market_pipeline`. El seed crea o actualiza exclusivamente `pipeline.MarketSource`; las
pantallas y catálogos de reseñas anteriores están ocultos. Verifica provider, `adapter_key`, URL,
país, límites y configuración primero con fixtures y luego con el dry-run del pipeline.

Los comandos legados siguientes se conservan sólo para diagnóstico de datos históricos, no para
dar de alta una fuente canónica:

```bash
.venv/bin/python manage.py run_review_scrape --source ID
.venv/bin/python manage.py run_review_scrape --provider codigo
.venv/bin/python manage.py enrich_reviews --limit 100
```
