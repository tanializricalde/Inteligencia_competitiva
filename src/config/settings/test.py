from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MIDDLEWARE = [item for item in MIDDLEWARE if item != "whitenoise.middleware.WhiteNoiseMiddleware"]  # noqa: F405
DATABASES["default"]["NAME"] = ":memory:"  # noqa: F405
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
