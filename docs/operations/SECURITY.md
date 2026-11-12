# Seguridad

- Autenticación por correo con mensajes indistinguibles; logout solo POST; recuperación estándar con token temporal.
- CSRF, `HttpOnly`, SameSite, `X-Content-Type-Options` y `X-Frame-Options` activos. En producción habilita HTTPS y cookies seguras desde entorno.
- Autorización se valida con permisos Django en cada view; ocultar controles no concede permisos.
- URLs solo HTTP/HTTPS, sin credenciales; IP privadas, loopback, link-local, reservadas y multicast se rechazan salvo `SCRAPER_ALLOW_PRIVATE_HOSTS=true` para pruebas controladas. La política actual no resuelve DNS antes de cada conexión: usa allowlists/red de egreso en producción para mitigar DNS rebinding.
- Respuestas se limitan por bytes, Content-Type y timeout. No se registran HTML completo, cookies, tokens ni credenciales.
- Evidencia Playwright se limita a screenshot visible y 100 KB de HTML escapado; el directorio debe tener retención/acceso restringido. No apuntes fuentes a páginas autenticadas.
- Adapter keys provienen de choices y un registro en código; nunca se importan módulos arbitrarios.
- `SECRET_KEY`, SMTP y hosts solo por entorno. `.env` está ignorado; `.env.example` no contiene secretos.
- En producción pública, Gunicorn se publica sólo en loopback y el proxy termina TLS. Mantén
  `SECURE_SSL_REDIRECT`, cookies seguras y orígenes CSRF HTTPS; valida con el preflight estricto. El
  perfil `--local-http`/`-LocalHttp` existe únicamente para evaluar la imagen en loopback sin
  dominio y nunca sustituye esa validación pública.
- No se admiten CAPTCHA, evasión anti-bot ni scraping sin autorización. Define User-Agent identificable y rate limit.

Amenazas prioritarias: SSRF, contenido hostil, fuga en errores/evidencia, escalación de permisos, duplicación del scheduler y tormenta de correos. Los controles correspondientes tienen pruebas o runbooks; la allowlist de egreso es defensa operativa adicional.

