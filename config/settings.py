"""Настройки проекта «Эврика».

Всё, что отличается между локальной разработкой и сервером, задаётся
переменными окружения (см. .env.example).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Задайте DJANGO_SECRET_KEY (или DJANGO_DEBUG=1 для локальной разработки).")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Каталог с данными, которые нельзя терять: база и загруженные работы.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "conference",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "conference.context_processors.conference",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        # Транзакции сразу берут блокировку записи: проверка свободных мест в секции
        # и сохранение заявки не перемешиваются между одновременными отправками.
        "OPTIONS": {"transaction_mode": "IMMEDIATE"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru"
TIME_ZONE = os.environ.get("TIME_ZONE", "Europe/Moscow")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Загруженные работы не раздаются напрямую: скачать их может только
# сотрудник через защищённую ссылку (conference.views.download_submission).
MEDIA_ROOT = DATA_DIR / "uploads"
MEDIA_URL = "/media/"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Почта для рассылок (поздравления допущенным). Способы по порядку:
#   1) свой SMTP-ящик: EMAIL_HOST и далее в .env;
#   2) sendmail на сервере (на хостинге Beget работает без настройки);
#   3) локально при DJANGO_DEBUG=1 письма печатаются в консоль.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", EMAIL_PORT == 465)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", EMAIL_PORT == 587)
EMAIL_TIMEOUT = 20
_site_host = next((h for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1") and not h.startswith("www.")), "")
DEFAULT_FROM_EMAIL = (
    os.environ.get("DEFAULT_FROM_EMAIL", "").strip()
    or EMAIL_HOST_USER
    or (f"Конференция «Эврика» <noreply@{_site_host}>" if _site_host else "webmaster@localhost")
)
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
elif DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    from conference.mailbackend import find_sendmail

    EMAIL_BACKEND = (
        "conference.mailbackend.SendmailBackend" if find_sendmail() else "django.core.mail.backends.dummy.EmailBackend"
    )
MAIL_CONFIGURED = EMAIL_BACKEND != "django.core.mail.backends.dummy.EmailBackend"

# Ограничение на размер файла работы, МБ.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    # Перенаправление HTTP → HTTPS делает Caddy (см. Caddyfile).
    SILENCED_SYSTEM_CHECKS = ["security.W008"]
