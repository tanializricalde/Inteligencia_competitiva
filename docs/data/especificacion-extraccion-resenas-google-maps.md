# Especificación de extracción de reseñas desde HTML

## 1. Objetivo

Esta especificación describe la estructura HTML observada, los datos que pueden extraerse y los selectores sugeridos para localizar cada elemento.

Los nombres de los datos se expresan en `snake_case`. Los selectores son orientativos: las clases CSS de Google Maps pueden cambiar, por lo que conviene priorizar atributos semánticos como `data-review-id`, `role`, `aria-label`, `lang` y `data-href`.

> **Condición de uso:** esta especificación solo debe aplicarse cuando exista autorización y el procesamiento cumpla las condiciones del sitio y la normativa aplicable.

## 2. Jerarquía general

```text
resumen_reviews
├── numero_reviews
├── calificacion_promedio
└── distribucion_calificaciones[]

lista_reviews
└── review[]
    ├── review_id
    ├── autor_nombre
    ├── autor_url
    ├── autor_id
    ├── autor_avatar_url
    ├── autor_numero_reviews
    ├── calificacion
    ├── fecha_relativa
    ├── texto_review
    ├── idioma_texto
    ├── es_traduccion
    └── respuesta_propietario
        ├── texto
        ├── fecha_relativa
        ├── idioma_texto
        └── es_traduccion
```

## 3. Resumen de reseñas

### 3.1 Datos principales

| Dato                    | Origen                         | Selector sugerido           | Transformación                                  |
| ----------------------- | ------------------------------ | --------------------------- | ----------------------------------------------- |
| `numero_reviews`        | Texto con el total de reseñas  | `.jANrlb .fontBodySmall`    | Extraer el número de un texto como `50 reviews` |
| `calificacion_promedio` | Texto de la puntuación general | `.jANrlb .fontDisplayLarge` | Convertir `4.8` a número decimal                |

Fragmento HTML relevante:

```html
<div class="jANrlb">
  <div class="fontDisplayLarge">{{calificacion_promedio}}</div>

  <div role="img" class="YTkVxc" aria-label="{{calificacion_promedio}} stars">
    ...
  </div>

  <div class="fontBodySmall">{{numero_reviews}} reviews</div>
</div>
```

`numero_reviews` debería obtenerse preferentemente del texto visible del total. Como validación secundaria se pueden sumar las cantidades de la distribución por estrellas, aunque ambos valores podrían no coincidir temporalmente si la página se actualiza o si el fragmento fue capturado parcialmente.

### 3.2 Distribución por puntuación

Aunque no se indicó originalmente como campo de salida, el HTML permite extraer la cantidad de reseñas correspondiente a cada puntuación.

| Dato                | Origen                                  | Selector sugerido                      | Ejemplo               |
| ------------------- | --------------------------------------- | -------------------------------------- | --------------------- |
| `calificacion`      | Primera celda de la fila o `aria-label` | `tr.BHOKXe > td:first-child`           | `5`                   |
| `numero_reviews`    | Atributo accesible de la fila           | `tr.BHOKXe[role="img"]` → `aria-label` | `5 stars, 43 reviews` |
| `porcentaje_visual` | Estilo de la barra                      | `.oxIpGd` → `style`                    | `padding-left: 100%`  |

Fragmento representativo:

```html
<tr
  class="BHOKXe"
  role="img"
  aria-label="{{calificacion}} stars, {{numero_reviews}} reviews"
>
  <td class="yxmtmf fontBodyMedium">{{calificacion}}</td>
  <td class="ZVa0Ic">
    <div class="XINzN">
      <div class="oxIpGd" style="padding-left: {{porcentaje_visual}}%;"></div>
    </div>
  </td>
</tr>
```

Estructura de salida sugerida:

```json
{
  "calificacion_promedio": 4.8,
  "numero_reviews": 50,
  "distribucion_calificaciones": [
    { "calificacion": 5, "numero_reviews": 43 },
    { "calificacion": 4, "numero_reviews": 5 },
    { "calificacion": 3, "numero_reviews": 2 },
    { "calificacion": 2, "numero_reviews": 0 },
    { "calificacion": 1, "numero_reviews": 0 }
  ]
}
```

## 4. Contenedor de la lista de reseñas

### 4.1 Dato

`lista_reviews`

Fragmento HTML observado:

```html
<div class="m6QErb XiKgde">...</div>
```

Selector inicial sugerido:

```css
div.m6QErb.XiKgde
```

Este selector puede coincidir con más de un contenedor de Google Maps. Antes de usarlo se debe verificar que el elemento localizado:

1. Sea desplazable verticalmente, teniendo en cuenta que el contener que contiene la barra de desplazamiento es `<div class="m6QErb DxyBCb kA9KIf dS8AEf XiKgde " tabindex="-1" jslog="26354;mutable:true;" style="">`, esta barra es la que es usada tambien para el cargado dinamico de mas reseñas.
2. Contenga elementos con `data-review-id`.
3. Contenga tarjetas que coincidan con `div.jftiEf[data-review-id]`.

Una búsqueda más segura consiste en localizar primero una tarjeta de reseña y después obtener su ancestro desplazable. No debe asumirse que la primera coincidencia de `.m6QErb.XiKgde` sea siempre la lista correcta.

## 5. Tarjeta individual de reseña

### 5.1 Identificación de la tarjeta

Dato principal: `review`

Selector sugerido:

```css
div.jftiEf[data-review-id]
```

Fragmento simplificado:

```html
<div
  class="jftiEf fontBodyMedium"
  aria-label="{{autor_nombre}}"
  data-review-id="{{review_id}}"
>
  ...
</div>
```

Cada tarjeta debe procesarse de forma independiente. Todos los selectores de los apartados siguientes deben evaluarse dentro de la tarjeta actual para evitar mezclar datos de diferentes reseñas.

### 5.2 Campos extraíbles sin ambigüedad relevante

| Dato                   | Fuente dentro de la tarjeta            | Selector sugerido                             | Transformación u observación                                  |
| ---------------------- | -------------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| `review_id`            | Atributo de la tarjeta                 | `[data-review-id]` → `data-review-id`         | Conservar como texto; sirve para deduplicar                   |
| `autor_nombre`         | Nombre visible                         | `.d4r55`                                      | Usar `textContent` normalizado                                |
| `autor_url`            | Enlace lógico del botón del autor      | `button.al6Kxe[data-href]` → `data-href`      | El elemento es un `button`, no necesariamente un enlace `<a>` |
| `autor_id`             | Segmento numérico de `autor_url`       | Extraer de `/maps/contrib/{autor_id}/reviews` | Derivado de `autor_url`                                       |
| `autor_avatar_url`     | Imagen del perfil                      | `img.NBa7we` → `src`                          | Puede ser una URL temporal o modificarse                      |
| `autor_numero_reviews` | Texto bajo el autor                    | `.RfnDt`                                      | Extraer el número de un texto como `1 review`                 |
| `calificacion`         | Etiqueta accesible de las estrellas    | `.kvMYJc[role="img"]` → `aria-label`          | Extraer `5` de `5 stars`                                      |
| `fecha_relativa`       | Texto junto a la puntuación            | `.rsqaWe`                                     | Ejemplo: `a year ago`; no equivale a una fecha exacta         |
| `texto_review`         | Texto actualmente mostrado             | `.MyEned .wiI7pd`                             | Se limita al comentario; puede ser una traducción automática  |
| `idioma_texto`         | Atributo del contenedor del comentario | `.MyEned[lang]` → `lang`                      | Ejemplo: `en`                                                 |
| `es_traduccion`        | Presencia del control de traducción    | `.oqftme button[aria-controls]`               | `true` si se muestra un control como `Translated by Google`   |

Una respuesta del propietario vive dentro de `.CDe7pd` y puede contener otra `.wiI7pd`. No es una
tarjeta ni una reseña adicional. Su texto debe extraerse como respuesta mediante
`.CDe7pd .wiI7pd`; su fecha relativa usa `.CDe7pd .DZSIDd`. La tarjeta principal se cuenta una sola
vez por el `data-review-id` del elemento `div.jftiEf` que contiene la calificación.

### 5.3 Fragmento HTML anotado

```html
<div
  class="jftiEf fontBodyMedium"
  aria-label="{{autor_nombre}}"
  data-review-id="{{review_id}}"
>
  <button
    class="WEBjve"
    data-review-id="{{review_id}}"
    data-href="{{autor_url}}"
    aria-label="Photo of {{autor_nombre}}"
  >
    <img class="NBa7we" src="{{autor_avatar_url}}" />
  </button>

  <button
    class="al6Kxe"
    data-review-id="{{review_id}}"
    data-href="{{autor_url}}"
  >
    <div class="d4r55 fontTitleMedium">{{autor_nombre}}</div>
    <div class="RfnDt">{{autor_numero_reviews}} review</div>
  </button>

  <div class="DU9Pgb">
    <span class="kvMYJc" role="img" aria-label="{{calificacion}} stars">
      ...
    </span>

    <span class="rsqaWe">{{fecha_relativa}}</span>
  </div>

  <div class="MyEned" id="ucc-3" lang="{{idioma_texto}}">
    <span class="wiI7pd">{{texto_review}}</span>
  </div>

  <div class="oqftme">
    <button role="switch" aria-controls="ucc-3" data-review-id="{{review_id}}">
      <span>Translated by Google</span>
      <span>See original (Spanish)</span>
    </button>
  </div>
</div>
```

## 6. Reglas especiales de extracción

### 6.1 Alcance de los selectores

Después de localizar una tarjeta, las consultas deben limitarse a ella:

```python
cards = page.locator(
    'div.jftiEf[data-review-id]:has(.kvMYJc[role="img"][aria-label])'
)

for index in range(await cards.count()):
    card = cards.nth(index)

    review_id = await card.get_attribute("data-review-id")
    autor_nombre = await card.locator(".d4r55").inner_text()
    texto_review = await card.locator(".MyEned .wiI7pd").inner_text()
    respuesta = card.locator(".CDe7pd .wiI7pd")
```

No se recomienda ejecutar `page.locator(".wiI7pd")` ni usar `.wiI7pd` sin el contenedor
`.MyEned`, porque una tarjeta puede incluir otra coincidencia para la respuesta del propietario.
También pueden existir reseñas sin texto u otros elementos opcionales.

### 6.2 Reseñas traducidas

En el ejemplo, `.wiI7pd` contiene el texto traducido al inglés y el atributo `lang="en"` describe el idioma actualmente mostrado. La presencia del texto `See original (Spanish)` indica que el comentario original estaba en español, pero esa frase puede variar según el idioma de la interfaz.

Por tanto:

- `texto_review` representa inicialmente el texto visible.
- `idioma_texto` representa el idioma del texto visible, no necesariamente el original.
- `es_traduccion` puede establecerse en `true` cuando exista el control para mostrar el original.
- `idioma_original` no debe inferirse únicamente mediante texto dependiente del idioma de interfaz, salvo que se implemente un analizador específico por localización.
- Para obtener `texto_original`, sería necesario activar el control `showReviewInOriginal`, esperar la actualización de la tarjeta y volver a leer `.wiI7pd`. Se debe comprobar el estado `aria-checked` antes y después, ya que su semántica puede cambiar.

### 6.3 Fecha

`fecha_relativa` contiene expresiones como `a year ago`; el fragmento no incluye una fecha absoluta verificable. No se debe convertir a una fecha exacta sin reconocer que el resultado será estimado.

Si se necesita una fecha derivada, conviene mantener ambos campos:

```json
{
  "fecha_relativa": "a year ago",
  "fecha_estimada": null
}
```

### 6.4 Campos no determinables con este fragmento

Los siguientes datos no pueden extraerse de forma fiable del HTML proporcionado:

- Fecha absoluta de publicación.
- Cantidad de `likes` de la reseña.
- URL directa para compartir la reseña.
- Texto original mientras solo esté renderizada la traducción.
- Sentimiento de la reseña.
- Identificador estable de empresa o proveedor al que pertenece la reseña.

Estos campos deben dejarse como `null` o ser obtenidos mediante otra etapa autorizada de recolección o procesamiento.

## 7. Estructura de salida recomendada

```json
{
  "review_id": "Ci9DQUlRQUNvZENodHljRjlvT2pjeU1uRk9ZazVCYlZWeFZHcExaMVppZUhWM01IYxAB",
  "autor_nombre": "Angie Ocampo",
  "autor_url": "https://www.google.com/maps/contrib/105911604622496548536/reviews?hl=en-GB",
  "autor_id": "105911604622496548536",
  "autor_avatar_url": "https://lh3.googleusercontent.com/...",
  "autor_numero_reviews": 1,
  "calificacion": 5,
  "fecha_relativa": "a year ago",
  "fecha_estimada": null,
  "texto_review": "The advice provided by Jhonny Miranda has been one of the best experiences...",
  "idioma_texto": "en",
  "es_traduccion": true,
  "texto_original": null,
  "idioma_original": null,
  "numero_likes": null,
  "respuesta_propietario": null,
  "sentimiento": null
}
```

## 8. Prioridad y estabilidad de selectores

Orden recomendado para elegir selectores:

1. `data-review-id`, porque identifica la reseña y permite deduplicarla.
2. Atributos semánticos: `role`, `aria-label`, `lang`, `aria-controls` y `data-href`.
3. Relaciones estructurales dentro de una tarjeta ya identificada.
4. Clases CSS como `.d4r55`, `.wiI7pd` o `.rsqaWe`, únicamente cuando no exista una alternativa semántica.
5. Texto visible, como `reviews`, `stars` o `See original`, como último recurso, ya que cambia con el idioma de la interfaz.

Los selectores deben centralizarse en una única configuración o clase adaptadora para facilitar su actualización cuando cambie el DOM.
