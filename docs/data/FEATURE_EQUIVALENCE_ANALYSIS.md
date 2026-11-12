# Auditoría de equivalencias de características

## Alcance y resultado

Esta auditoría compara `data/clean/features.csv` con las salidas anteriores de
`data/normalized-legado/`. El input contiene 367 filas, 27 planes y cuatro competidores. La vista
ancha legada tenía 115 columnas: dos claves y 113 columnas creadas literalmente desde los textos.
Eso separaba capacidades equivalentes por diferencias de redacción, cantidades, mayúsculas o
nombre comercial.

La configuración revisada conserva intacta la tabla larga y aplica equivalencias sólo a la vista
ancha. Sobre los datos auditados elimina un duplicado exacto, procesa 366 observaciones, consume
316 mediante reglas y deja 50 observaciones en 22 columnas dinámicas. La vista ancha resultante
tiene 64 columnas totales. No se detectaron conflictos, capturas inválidas, colisiones ni
competidores desconocidos.

Las equivalencias se aceptaron cuando los textos describen la misma capacidad funcional. Una
columna amplia como `modulo_reportes` indica disponibilidad, pero no afirma que dos productos
tengan el mismo catálogo o cantidad de reportes. Cantidades y alcances específicos siguen
disponibles en la tabla larga. No se fusionaron términos cercanos cuando hacerlo podía inventar
significado.

## Matriz de trazabilidad

Cada celda contiene el `nombre_modulo` real que alimenta la columna normalizada. `—` significa que
el input actual no contiene una observación equivalente para ese competidor; no significa que el
producto carezca necesariamente de esa capacidad.

| Columna normalizada | Anfibius | iDrix Contable | Perseo | Siigo |
| --- | --- | --- | --- | --- |
| `usuarios_normales` | — | Usuarios: 10<br>Usuarios: 2<br>Usuarios: 3<br>Usuarios: 5 | — | 2 usuarios \| 1 usuario contador<br>3 usuarios \| 1 usuario contador<br>5 usuarios \| 1 usuario contador |
| `usuarios_contador` | — | Usuarios contador: 1 | — | 2 usuarios \| 1 usuario contador<br>3 usuarios \| 1 usuario contador<br>5 usuarios \| 1 usuario contador |
| `usuarios_sin_clasificar` | — | — | 6 Usuarios<br>Usuarios (4) / Aplicación móvil (1) | — |
| `usuarios_app_movil` | — | — | 1 Licencias App PerseoMóvil<br>2 Licencia App PerseoMóvil<br>2 Licencias App PerseoMóvil<br>Usuarios (4) / Aplicación móvil (1) | — |
| `app_movil_incluida` | — | App iDrix | 1 Licencias App PerseoMóvil<br>2 Licencia App PerseoMóvil<br>2 Licencias App PerseoMóvil<br>Usuarios (4) / Aplicación móvil (1) | App Contífico |
| `modulos_adicionales_por_consultar` | — | — | Consulta sobre módulos adicionales<br>¡Consulta sobre módulos adicionales! | — |
| `nomina_incluida` | — | Nómina (10 personas)<br>Nómina (15 personas)<br>Nómina (20 personas)<br>Nómina (5 personas) | Nómina | Nómina de 15 personas*<br>Nómina de 5 personas* |
| `nomina_personas_max` | — | Nómina (10 personas)<br>Nómina (15 personas)<br>Nómina (20 personas)<br>Nómina (5 personas) | — | Nómina de 15 personas*<br>Nómina de 5 personas* |
| `modulo_facturacion` | emisión de comprobantes electrónicos autorizados por el SRI | Facturación Electrónica | Facturación Electrónica Ilimitada<br>Facturación Electrónica ilimitada | Facturación electrónica ilimitada |
| `modulo_fiscal` | — | Conexión SRI y Registro Civil | — | — |
| `modulo_inventario` | gestión de inventarios | Inventario | Productos, Inventarios y Kárdex | Manejo de inventarios |
| `modulo_contabilidad` | integración completa con sistema contable en la nube | Contabilidad | Contabilidad integrada | Contabilidad y gestión de cartera |
| `centro_de_costos` | — | — | Centro de costos | — |
| `modulo_bancos` | integración con cuentas bancarias | Bancos | — | Módulo de Bancos |
| `modulo_conciliacion_bancaria` | conciliación básica | — | Conciliaciones bancarias | — |
| `modulo_activos_fijos` | — | Activos Fijos | — | Activos fijos<br>Activos fijos* |
| `modulo_importaciones` | — | Importaciones | — | Módulo de importaciones |
| `modulo_tesoreria` | — | Tesorería | Tesorería | — |
| `modulo_inteligencia_negocios` | — | Business Intelligence | 24 Gráficos BI Gerenciales<br>24 Gráficos de BI / Dash Board<br>36 Gráficos BI Gerenciales<br>36 Gráficos de BI / Dash Board<br>Conexión PowerBI<br>Más de 60 Reportes / 36 Gráficos de BI | — |
| `modulo_reportes` | reportes fiscales periódicos | Informes Gerenciales | Más de 60 Reportes / 36 Gráficos de BI | +20 reportes<br>+20 reportes financieros, contables y comerciales<br>+30 reportes financieros, contables y comerciales |
| `modulo_capacitacion` | capacitación | — | Capacitaciones Zoom Diarias<br>Video Tutoriales<br>Video Tutoriales y Capacitaciones Zoom | — |
| `modulo_soporte` | SLA prioritario<br>soporte limitado<br>soporte técnico 24/7 | — | Soporte Técnico Continuo | — |
| `modulo_produccion` | — | — | Producción | Módulo de producciones |
| `modulo_bodegas` | — | — | Manejo de Bodegas y Sucursales | Manejo de bodega (1)<br>Manejo de bodegas |
| `modulo_liquidacion_tarjetas` | — | Liquidación de Tarjetas de Crédito | — | Liquidación de tarjetas de crédito |
| `modulo_compras` | — | Compras | Compras de Productos y Servicios | — |
| `modulo_cartera` | — | — | Cuentas por cobrar y pagar | Contabilidad y gestión de cartera<br>Gestión de cartera |
| `modulo_facturacion_lote` | — | — | — | Facturación de lote: 100 documentos recurrentes<br>Facturación en lote<br>Facturación en lote: 2.500 documentos recurrentes |
| `modulo_catalogo_productos` | — | — | — | Creación de servicios y productos<br>Creación servicio y productos |
| `modulo_guia_remision` | — | — | — | Guía de remisión |
| `modulo_proformas` | — | — | — | Manejo de proformas |
| `modulo_variantes` | — | — | — | Módulo de variantes |
| `modulo_api` | — | — | — | API Key<br>API Key (1)<br>API Key (Ilimitado) |
| `modulo_punto_venta` | — | — | Punto de Venta<br>Punto de Venta Offline | — |
| `modulo_multiempresa` | — | — | Multiempresa | — |
| `modulo_restaurantes` | — | — | Módulo para Restaurantes | — |
| `modulo_tienda_online` | — | — | Tienda Online Integrada | — |

`usuarios_totales`, `total_modulos` y `lista_modulos` son derivados: no corresponden a un texto
individual. La primera suma los cuatro tipos de usuarios; las otras dos cuentan y enumeran las
columnas booleanas etiquetadas como módulos. `app_movil_incluida` y
`modulos_adicionales_por_consultar` no se cuentan como módulos para no inflar esa métrica.

## Conceptos pendientes de decisión manual

Estas 22 claves permanecen como columnas dinámicas porque son capacidades exclusivas en la muestra
o porque la equivalencia sugerida perdería una diferencia relevante:

| Clave dinámica | Filas | Motivo para no fusionarla automáticamente |
| --- | ---: | --- |
| `actualizaciones` | 6 | No declara frecuencia; no equivale necesariamente a actualizaciones automáticas semanales. |
| `ventas` | 4 | Sólo observada en iDrix; falta una contraparte explícita en otros proveedores. |
| `tributacion` | 4 | Es más amplia que ATS, reportes fiscales o conexión SRI. |
| `auditorias_del_sistema` | 4 | Capacidad exclusiva observada en iDrix. |
| `robot_descargar_facturas_sri` | 4 | Automatización específica, distinta de conexión SRI o tributación. |
| `envio_de_documentos_por_whatsapp` | 4 | Canal específico sin equivalente observado. |
| `actualizaciones_automaticas_semanales` | 3 | Conserva frecuencia y automatización, ausentes en `actualizaciones`. |
| `1_licencia_en_el_servidor` | 3 | Una licencia técnica no debe sumarse como usuario sin validar el licenciamiento. |
| `gestion_de_lotes_fechas_de_caducidad` | 3 | Puede ser subcapacidad de inventario, pero la muestra no confirma cobertura equivalente. |
| `ats_anexo_transaccional` | 3 | Entregable tributario específico, no sinónimo de tributación completa. |
| `presupuestos` | 1 | Capacidad exclusiva observada en iDrix. |
| `imagenes_de_productos_hasta_2000_skus` | 1 | Incluye un límite y no equivale al catálogo general. |
| `almacenamiento_minimo_en_la_nube` | 1 | No existe cantidad recuperada ni contraparte comparable. |
| `respaldo_automatico` | 1 | Capacidad operativa exclusiva observada en Anfibius. |
| `automatizacion_de_asientos` | 1 | Función contable específica; fusionarla con contabilidad ocultaría el alcance. |
| `multiusuario` | 1 | No aporta cantidad y no debe convertirse en un número de usuarios. |
| `acompanamiento_en_la_adopcion_del_software` | 1 | Servicio de adopción distinto de soporte o capacitación puntual. |
| `1_licencia_de_estacion_de_trabajo` | 1 | Licencia de dispositivo; relación con usuarios no confirmada. |
| `2_licencias_de_estaciones_de_trabajo` | 1 | Licencia de dispositivo; relación con usuarios no confirmada. |
| `3_licencias_de_estaciones_de_trabajo` | 1 | Licencia de dispositivo; relación con usuarios no confirmada. |
| `perseohybrid` | 1 | Nombre comercial sin descripción funcional suficiente. |
| `version_pc_y_web_al_mismo_tiempo` | 1 | Modalidad técnica sin equivalente explícito observado. |

Una revisión comercial puede promover cualquiera de estas claves a columna canónica. Para hacerlo,
debe definir si se busca disponibilidad general, nivel de servicio o una cantidad, y conservar en
columnas separadas cualquier frecuencia, límite o modalidad que afecte la comparación.

## Reproducción

Linux:

```bash
.venv/bin/python -m data_transformation data/clean/features.csv \
  --type feature \
  --output data/normalized-equivalencias/features.csv \
  --wide-output data/normalized-equivalencias/features-wide.csv \
  --report data/normalized-equivalencias/quality-report.json \
  --feature-rules feature_rules/feature-equivalence.example.json \
  --feature-rules-report data/normalized-equivalencias/feature-rules-report.json
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m data_transformation .\data\clean\features.csv `
  --type feature `
  --output .\data\normalized-equivalencias\features.csv `
  --wide-output .\data\normalized-equivalencias\features-wide.csv `
  --report .\data\normalized-equivalencias\quality-report.json `
  --feature-rules .\feature_rules\feature-equivalence.example.json `
  --feature-rules-report .\data\normalized-equivalencias\feature-rules-report.json
```
