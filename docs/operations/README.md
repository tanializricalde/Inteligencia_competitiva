# Operación y producción

- [Producción desde cero](PRODUCTION.md): secuencias Linux/Windows, verificación y ciclo de vida.
- [Despliegue con Nginx](DEPLOYMENT_NGINX.md): Linux, TLS, actualización, assets y rollback.
- [Operación](OPERATIONS.md): scheduler, salud, backups, restauración e incidentes.
- [Seguridad](SECURITY.md): secretos, SSRF, permisos y evidencia.
- [Uso de recursos](RESOURCE_USAGE.md): concurrencia y comandos costosos.

Linux con Nginx/Certbot es el host canónico. Windows puede ejecutar el mismo runtime con Docker
Desktop y un proxy TLS del host, con las limitaciones descritas en la guía. No ejecutes migraciones
concurrentes ni más de un scheduler, y no elimines volúmenes durante despliegue o diagnóstico.
