from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[3]
env = environ.Env(
    DEBUG=(bool, False),
    SCRAPER_MAX_RESPONSE_BYTES=(int, 5_000_000),
    SCRAPER_ALLOW_PRIVATE_HOSTS=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="unsafe-development-only-key")
DEBUG = env.bool("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=['localhost', '127.0.0.1'])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
APP_BASE_URL = env("APP_BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.market",
    "apps.scraping",
    "apps.reviews",
    "apps.pipeline",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "src" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.market.branding.application_branding_context",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_PATH = Path(
    str(env.path("DATABASE_PATH", default=BASE_DIR / "data" / "market-watch.sqlite3"))
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATABASE_PATH,
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "es"
TIME_ZONE = env("APP_TIME_ZONE", default="America/Lima")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "src" / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = env.path("MEDIA_ROOT", default=BASE_DIR / "media")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.test")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SCRAPER_USER_AGENT = env("SCRAPER_USER_AGENT", default="MarketWatch/0.1")
SCRAPER_MAX_RESPONSE_BYTES = env.int("SCRAPER_MAX_RESPONSE_BYTES")
SCRAPER_EVIDENCE_DIR = env.path("SCRAPER_EVIDENCE_DIR", default=BASE_DIR / "evidence")
SCRAPER_ALLOW_PRIVATE_HOSTS = env.bool("SCRAPER_ALLOW_PRIVATE_HOSTS")
PIPELINE_ARTIFACT_ROOT = env.path("PIPELINE_ARTIFACT_ROOT", default=BASE_DIR / "data" / "pipeline")

UNFOLD = {
    "SITE_TITLE": "apps.market.branding.admin_site_title",
    "SITE_HEADER": "apps.market.branding.admin_site_title",
    "SITE_LOGO": "apps.market.branding.admin_site_logo",
    "SITE_ICON": "apps.market.branding.admin_site_icon",
    "SITE_FAVICONS": "apps.market.branding.admin_site_favicons",
    "SITE_SYMBOL": "monitoring",
    "COLORS": {"primary": {"600": "37 99 235"}},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"context": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "context"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
