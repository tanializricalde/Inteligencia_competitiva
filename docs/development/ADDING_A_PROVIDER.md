# Desarrollo aislado de un provider

Un *provider* es un adaptador que convierte la respuesta de una fuente externa al contrato común `ScrapedPlanDTO`. La forma recomendada de desarrollarlo es por capas: primero parser y contrato con fixtures locales, luego registro e integración, y únicamente al final una prueba manual autorizada. No hace falta ejecutar Django web, el scheduler ni una base de datos para desarrollar el adaptador.

## 1. Condiciones previas

Antes de escribir código:

1. Confirma autorización, términos/robots, frecuencia y datos permitidos.
2. Documenta la URL objetivo, campos esperados, moneda, periodicidad e identificador estable del plan.
   La periodicidad no debe incorporarse al ID cuando mensual y anual son opciones comerciales del
   mismo plan; en ese caso consolida ambas observaciones en los campos de precio del mismo DTO y
   valida que nombre, producto, moneda y características sean compatibles.
3. Elige HTTPX si el servidor entrega el HTML útil; usa Playwright solo cuando JavaScript sea imprescindible.
4. Define una clave corta y estable en `snake_case`, por ejemplo `acme_httpx`. Esa clave persistirá en la base.
5. No implementes login, CAPTCHA ni evasión anti-bot. No guardes cookies, tokens, datos personales o HTML sensible como fixture.

## 2. Unidad independiente de trabajo

Para `acme_httpx`, limita inicialmente los cambios a:

```text
src/apps/scraping/infrastructure/providers/acme_httpx.py
tests/fixtures/providers/acme_plans.html
tests/scraping/test_acme_httpx_adapter.py
```

Crea una fixture HTML mínima, sintética o anonimizada, que represente únicamente la estructura necesaria. Añade fixtures separadas para estructura cambiada o resultado vacío cuando ayuden a leer las pruebas. Las pruebas no deben consultar Internet.

Usa como referencias ejecutables:

- [`example_httpx.py`](../../src/apps/scraping/infrastructure/providers/example_httpx.py) y [`test_httpx_adapter.py`](../../tests/scraping/test_httpx_adapter.py) para descarga HTTP inyectable y parsing;
- [`legacy_pricing.py`](../../src/scraping_core/adapters/legacy_pricing.py) y [`test_legacy_pricing_adapters.py`](../../tests/scraping/test_legacy_pricing_adapters.py) para tarjetas WordPress con varios precios y transporte HTTPX/Playwright según la fuente;
- [`siigo_plans.py`](../../src/scraping_core/adapters/siigo_plans.py) y [`test_siigo_adapter.py`](../../tests/scraping/test_siigo_adapter.py) para JSON estructurado en `__NEXT_DATA__` sin duplicar red entre CLI y Django;
- [`idrixcontable_plans.py`](../../src/scraping_core/adapters/idrixcontable_plans.py) y [`test_idrixcontable_adapter.py`](../../tests/scraping/test_idrixcontable_adapter.py) para paneles dinámicos con un sufijo de `id` estable y transporte Playwright compartido;
- [`example_playwright.py`](../../src/apps/scraping/infrastructure/providers/example_playwright.py) y [`test_playwright_adapter.py`](../../tests/scraping/test_playwright_adapter.py) para una página JavaScript servida desde `127.0.0.1` durante la prueba;
- [`test_playwright_cleanup.py`](../../tests/scraping/test_playwright_cleanup.py) para verificar cierre de página, contexto y navegador.

## 3. Implementar el contrato

El adaptador debe exponer una clave y devolver exclusivamente DTOs comunes:

```python
class AcmeHttpxProviderScraper:
    adapter_key = "acme_httpx"

    def scrape(self, source: ScrapeSourceDTO) -> list[ScrapedPlanDTO]:
        ...
```

Cada `ScrapedPlanDTO` debe incluir:

- `external_id` estable cuando la fuente lo proporcione;
- nombre original y normalizado;
- producto o familia del producto (`product`) cuando la fuente lo exponga;
- precio como `Decimal | None`, moneda y periodicidad canónica;
- texto original del precio;
- características normalizadas con `{state, value, original}`;
- URL de origen y un `raw_payload` mínimo, sin secretos ni HTML completo.

Reutiliza `normalize_name` sólo para `normalized_name`, comparaciones, claves o identidad;
`original_name`, textos, moneda, producto, características originales y `raw_payload` deben
conservar el valor observado. Usa `parse_price`, `normalize_periodicity`, `FeatureState` y
`FeatureValue` cuando el contrato tipado lo requiera. Valida solo claves conocidas de
`source.config`. Mantén configurables timeout y reintentos, respeta
`SCRAPER_MAX_RESPONSE_BYTES` y usa el `User-Agent` configurado.

Transforma fallos externos en errores del dominio:

- `ScrapeTimeoutError` o `TransportError` para transporte;
- `AccessBlockedError` para 401/403;
- `HttpResponseError` para estado o Content-Type inválido;
- `ResponseTooLargeError` para respuestas fuera del límite;
- `StructureChangedError` cuando faltan nodos obligatorios;
- `NormalizationError` cuando un valor requerido no se puede normalizar;
- `SuspiciousEmptyResultError` cuando una página válida produce cero planes.

## 4. Pruebas offline dirigidas

Para HTTPX, inyecta `httpx.Client(transport=httpx.MockTransport(handler))`; así se prueban descarga y parser sin DNS ni red. Cubre como mínimo:

1. éxito y contenido exacto de los DTO;
2. timeout y cantidad de reintentos;
3. HTTP transitorio con reintento y no transitorio sin reintento;
4. Content-Type o tamaño inválido;
5. estructura cambiada;
6. precio, periodicidad o característica inválida;
7. cero resultados como error sospechoso;
8. cierre del cliente si el adaptador lo creó.

Ejecuta únicamente el provider mientras iteras:

```bash
.venv/bin/python -m pytest tests/scraping/test_acme_httpx_adapter.py -q
```

Para Playwright, sirve la fixture con un servidor HTTP local sobre un puerto efímero, activa `settings.SCRAPER_ALLOW_PRIVATE_HOSTS = True` solo dentro de la prueba y márcala con `@pytest.mark.playwright`. No uses `file://` ni una URL pública.

```bash
.venv/bin/python -m pytest tests/scraping/test_acme_playwright_adapter.py -q
```

El patrón completo está en `tests/scraping/test_playwright_adapter.py`. Añade además pruebas de timeout, evidencia sanitizada y cleanup. Ejecuta Chromium en serie.

## 5. Registrar el provider al final

Cuando las pruebas aisladas pasen:

1. Exporta/importa la clase según corresponda en `providers/`.
2. Registra explícitamente su factory en `src/apps/scraping/infrastructure/builtin.py`.
3. Añade `(adapter_key, etiqueta)` a `ScrapeSource.ADAPTER_CHOICES`.
4. Genera y revisa la migración de la elección:

```bash
.venv/bin/python manage.py makemigrations scraping
.venv/bin/python manage.py migrate
.venv/bin/python manage.py makemigrations --check --dry-run
```

Nunca importes una clase desde una ruta almacenada en base de datos. El registro explícito es el límite de seguridad.

Verifica registro y regresiones sin navegador:

```bash
.venv/bin/python -m pytest tests/scraping/test_registry.py tests/scraping/test_acme_httpx_adapter.py -q
make lint
make test
```

Si el provider usa Playwright, ejecuta después su archivo dirigido y finalmente `make test-playwright`.

## 6. Integración controlada con la aplicación

Solo después de completar la fase offline:

1. Crea el `Provider` y el `ScrapeSource` desde el admin.
2. Mantén la fuente deshabilitada mientras revisas URL, autorización, límites, selectores y `config`.
3. Una prueba manual desde la interfaz requiere activar esa fuente. Actívala durante una ventana controlada, solicita únicamente esa fuente y procésala con el scheduler ya iniciado o una ejecución única:

```bash
.venv/bin/python manage.py run_scheduler --once
```

4. Revisa el detalle de la ejecución, planes, snapshots, cambios, evidencia y outbox. No consideres éxito únicamente un HTTP 200.
5. Desactiva de nuevo la fuente mientras corriges cualquier hallazgo. Actívala permanentemente solo cuando la frecuencia y las alertas estén aprobadas.

`run_scheduler --once` procesa como máximo una solicitud manual pendiente y termina. Si ya hay otro scheduler activo, el lock impedirá ejecutar una segunda instancia; en ese caso deja que el proceso existente atienda la solicitud.

## 7. Criterio de terminado

Un provider está listo cuando:

- todas sus pruebas usan fixtures locales y son deterministas;
- cumple el contrato DTO y la taxonomía de errores;
- no registra ni conserva secretos o contenido sensible;
- registro, choices y migración son coherentes;
- `make lint`, `make test` y, si aplica, `make test-playwright` pasan;
- la fuente real autorizada tuvo una ejecución manual revisada antes de programarse.

Consulta también [Guía de desarrollo](DEVELOPMENT.md), [Seguridad](../operations/SECURITY.md) y [Operación](../operations/OPERATIONS.md).
