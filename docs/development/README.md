# Desarrollo: punto de entrada

Elige el recorrido del sistema donde ejecutarás Django:

- [Linux desde cero](LINUX.md): entorno nativo recomendado, Django, scheduler, frontend y Docker.
- [Windows desde cero](WINDOWS.md): PowerShell, entorno nativo, Django, scheduler, frontend y Docker Desktop.
- [Guía de desarrollo](DEVELOPMENT.md): usuarios, datos, flujo diario, persistencia y diagnóstico.
- [Variables de entorno](ENVIRONMENT_VARIABLES.md): tipos, defaults, ejemplos y diferencias de rutas Linux/Windows/Docker.
- [Equivalencias Linux/Windows](WINDOWS_LINUX.md): referencia rápida de rutas y sintaxis.

La aplicación web y el scheduler son procesos distintos. En desarrollo deben permanecer abiertos en
dos terminales y compartir el mismo `.env` y la misma base. `Ctrl+C` detiene cada proceso nativo sin
eliminar datos.

Si sólo cambias `frontend/`, recompila los assets antes de validar la interfaz. No edites
`src/static/dist/` a mano: es una salida generada.

Para producción empieza en [Producción desde cero](../operations/PRODUCTION.md). Linux con Nginx es
la ruta canónica; Windows puede ejecutar el runtime en Docker Desktop si aporta el proxy TLS y el
arranque automático descritos en esa guía.
