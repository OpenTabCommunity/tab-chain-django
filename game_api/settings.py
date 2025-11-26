import os
from pathlib import Path
import environ
from datetime import timedelta

# Base setup
BASE_DIR = Path(__file__).resolve().parent

env = environ.Env(
    DEBUG=(bool, True),

    # Existing
    AI_TIMEOUT=(float, 5.0),
    AI_MAX_RETRIES=(int, 3),
    LEADERBOARD_LIMIT=(int, 50),

    # ---- Added AI client settings ----
    AI_SERVICE_URL=(str, "http://localhost:11434"),
    AI_MODEL=(str, "gemma3"),
    AI_MAX_TOKENS=(int, 120),
    AI_STOP=(str, '["\\n\\n"]'),  # stored as JSON string

    # Circuit-breaker
    AI_CIRCUIT_THRESHOLD=(int, 6),
    AI_CIRCUIT_COOLDOWN=(float, 30.0),

    # HTTP connection limits
    AI_MAX_KEEPALIVE=(int, 10),
    AI_MAX_CONNECTIONS=(int, 50),

    # Allowed moves (stored as string → parsed later)
    AI_ALLOWED_MOVES=(str, '["rock", "paper", "scissors"]'),

    # Optional logging flag
    AI_LOG_LEVEL=(str, "INFO"),

    # Optional API key
    AI_API_KEY=(str, None),
)

# Read environment variables from .env file
env.read_env(BASE_DIR / ".env")

# Basic Django settings
SECRET_KEY = env("SECRET_KEY", default="unsafe-secret-key")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

# Installed apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",

    # Local apps
    "users",
    "game",
]

# Middleware
MIDDLEWARE = [
    "game_api.middleware.SimpleCorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "game_api.urls"

# Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "game_api.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER", default=""),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default=""),
        "PORT": env("DB_PORT", default=""),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Localization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication
AUTH_USER_MODEL = "users.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
}
# External AI Service Config
AI_SERVICE_URL = env("AI_SERVICE_URL", default="")
AI_API_KEY = env("AI_API_KEY", default="")
AI_TIMEOUT = env("AI_TIMEOUT")
AI_MAX_RETRIES = env("AI_MAX_RETRIES")

# Game Config
LEADERBOARD_LIMIT = env("LEADERBOARD_LIMIT")
VALID_MOVES = ["rock", "paper", "scissors"]

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "game": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "ai_client": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}


AI_SERVICE_URL = env("AI_SERVICE_URL")
AI_MODEL = env("AI_MODEL")
AI_MAX_TOKENS = env("AI_MAX_TOKENS")
AI_TIMEOUT = env("AI_TIMEOUT")
AI_MAX_RETRIES = env("AI_MAX_RETRIES")

AI_CIRCUIT_THRESHOLD = env("AI_CIRCUIT_THRESHOLD")
AI_CIRCUIT_COOLDOWN = env("AI_CIRCUIT_COOLDOWN")

AI_MAX_KEEPALIVE = env("AI_MAX_KEEPALIVE")
AI_MAX_CONNECTIONS = env("AI_MAX_CONNECTIONS")

AI_LOG_LEVEL = env("AI_LOG_LEVEL")
AI_API_KEY = env("AI_API_KEY")

