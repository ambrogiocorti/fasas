"""
Impostazioni del sistema FASAS Digitale.

Tutta la configurazione sensibile arriva da variabili d'ambiente (vedi .env.example).
In produzione il database è PostgreSQL (Supabase) tramite DATABASE_URL.
"""
import codecs
import io
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Legge .env in UTF-8 o UTF-16 (su Windows PowerShell salva «echo ... > .env» in UTF-16)."""
    if not path.exists():
        return
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig"
    load_dotenv(stream=io.StringIO(raw.decode(encoding)))


load_env_file(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY deve essere impostata in produzione")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework.authtoken",
    "fasas.core",
    "fasas.accounts",
    "fasas.audit",
    "fasas.guests",
    "fasas.documents",
    "fasas.signatures",
    "fasas.pharmacy",
    "fasas.clinical",
    "fasas.daily",
    "fasas.protocols",
    "fasas.appointments",
    "fasas.pai",
    "fasas.notifications",
    "fasas.reports",
    "fasas.backups",
    "fasas.search",
    "fasas.imports",
    "fasas.offline",
    "fasas.billing",
    "fasas.staffing",
    "fasas.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "fasas.core.middleware.AllowedNetworksMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "fasas.core.middleware.CommunityMiddleware",
    "fasas.core.middleware.SessionIdleTimeoutMiddleware",
    "fasas.audit.middleware.AuditContextMiddleware",
    "fasas.core.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"
SERIALIZATION_MODULES = {"fasasjson": "fasas.core.exactjson"}  # backup JSON con orari esatti (microsecondi)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "fasas.core.context_processors.fasas",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.environ.get("DATABASE_CONN_MAX_AGE", "60")),
        ssl_require=env_bool("DATABASE_SSL_REQUIRE", False),
    )
}
# Ogni richiesta è atomica: una modifica e il suo audit log vengono salvati insieme o per niente.
DATABASES["default"]["ATOMIC_REQUESTS"] = True
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    # SQLite (prove e sviluppo): transazioni IMMEDIATE evitano «database is locked» con richieste contemporanee
    DATABASES["default"].setdefault("OPTIONS", {}).update({"transaction_mode": "IMMEDIATE", "timeout": 20})

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["fasas.accounts.backends.FasasPermissionBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# I file caricati sono sempre cifrati prima di essere scritti sullo storage
# e non sono mai serviti direttamente: passano da viste autenticate e tracciate.
MEDIA_ROOT = Path(os.environ.get("FASAS_MEDIA_ROOT", BASE_DIR / "media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if os.environ.get("FASAS_S3_BUCKET"):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.environ["FASAS_S3_BUCKET"],
            "endpoint_url": os.environ.get("FASAS_S3_ENDPOINT_URL") or None,
            "region_name": os.environ.get("FASAS_S3_REGION") or None,
            "default_acl": "private",
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Sicurezza -------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Sistema interno della comunità: non va inserito nella lista HSTS preload dei browser.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^salute/$"]  # il controllo di salute arriva anche in HTTP interno (container, proxy)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Chiavi di cifratura dei file (Fernet, separate da virgola: la prima cifra, le altre decifrano
# per consentire la rotazione). Generare con: python manage.py fasas_genkey
FASAS_ENCRYPTION_KEYS = env_list("FASAS_ENCRYPTION_KEYS")
# Chiave AES-256 dei backup (base64 url-safe, 32 byte). Va conservata fuori dal server.
FASAS_BACKUP_KEY = os.environ.get("FASAS_BACKUP_KEY", "")
FASAS_BACKUP_DIR = Path(os.environ.get("FASAS_BACKUP_DIR", BASE_DIR / "backups"))
# Copia fuori sede su object storage compatibile S3 in UE, con blocco delle modifiche (docs/BACKUP.md)
FASAS_OFFSITE_ENDPOINT = os.environ.get("FASAS_OFFSITE_ENDPOINT", "")  # es. https://s3.<regione>.<fornitore>
FASAS_OFFSITE_REGION = os.environ.get("FASAS_OFFSITE_REGION", "")
FASAS_OFFSITE_BUCKET = os.environ.get("FASAS_OFFSITE_BUCKET", "")
FASAS_OFFSITE_ACCESS_KEY = os.environ.get("FASAS_OFFSITE_ACCESS_KEY", "")
FASAS_OFFSITE_SECRET_KEY = os.environ.get("FASAS_OFFSITE_SECRET_KEY", "")
FASAS_OFFSITE_PREFIX = os.environ.get("FASAS_OFFSITE_PREFIX", "fasas")
FASAS_OFFSITE_LOCK_DAYS = int(os.environ.get("FASAS_OFFSITE_LOCK_DAYS", "30"))
FASAS_OFFSITE_LOCK_MODE = os.environ.get("FASAS_OFFSITE_LOCK_MODE", "COMPLIANCE")  # COMPLIANCE | GOVERNANCE
FASAS_OFFSITE_KEEP_DAILY = int(os.environ.get("FASAS_OFFSITE_KEEP_DAILY", "30"))
FASAS_OFFSITE_KEEP_MONTHLY = int(os.environ.get("FASAS_OFFSITE_KEEP_MONTHLY", "12"))
# Database vuoto su cui provare il ripristino dei backup PostgreSQL (prova trimestrale). Vuoto = prova parziale.
FASAS_RESTORE_TEST_DATABASE_URL = os.environ.get("FASAS_RESTORE_TEST_DATABASE_URL", "")
# Reti autorizzate (CIDR). Vuoto = nessuna restrizione di rete applicativa.
FASAS_ALLOWED_NETWORKS = env_list("FASAS_ALLOWED_NETWORKS")
FASAS_TRUSTED_PROXY_COUNT = int(os.environ.get("FASAS_TRUSTED_PROXY_COUNT", "0"))
# Tentativi di accesso falliti prima del blocco temporaneo
FASAS_LOGIN_MAX_FAILURES = int(os.environ.get("FASAS_LOGIN_MAX_FAILURES", "5"))
FASAS_LOGIN_LOCKOUT_MINUTES = int(os.environ.get("FASAS_LOGIN_LOCKOUT_MINUTES", "15"))
# Verifica in due passaggi (codice dall'app sul telefono): obbligatoria per questi ruoli; vuoto = facoltativa per tutti
FASAS_2FA_REQUIRED_ROLES = env_list("FASAS_2FA_REQUIRED_ROLES", "admin,coordinator,doctor")
# Reti della struttura (CIDR): da fuori serve sempre la verifica, e la si può attivare solo da dentro. Vuoto = ovunque.
FASAS_2FA_TRUSTED_NETWORKS = env_list("FASAS_2FA_TRUSTED_NETWORKS")
FASAS_2FA_ISSUER = os.environ.get("FASAS_2FA_ISSUER", "FASAS")
# Firma digitale (docs/FIRMA_DIGITALE.md). Ogni medico sceglie il proprio strumento: certificato PKCS#12
# o firma remota qualificata presso un prestatore (QTSP) tramite API CSC.
FASAS_SIGNATURE_TSA_URL = os.environ.get("FASAS_SIGNATURE_TSA_URL", "")  # marca temporale RFC 3161
FASAS_SIGNATURE_TSA_USER = os.environ.get("FASAS_SIGNATURE_TSA_USER", "")
FASAS_SIGNATURE_TSA_PASSWORD = os.environ.get("FASAS_SIGNATURE_TSA_PASSWORD", "")
# Punti di controllo notturni dell'audit con marca temporale della TSA qui sopra (se configurata)
FASAS_AUDIT_TIMESTAMP = env_bool("FASAS_AUDIT_TIMESTAMP", True)
FASAS_SIGNATURE_LEVEL = os.environ.get("FASAS_SIGNATURE_LEVEL", "")  # B-B, B-T, B-LT, B-LTA (vuoto: B-T se c'è la TSA)
FASAS_SIGNATURE_TRUST_ROOTS = os.environ.get("FASAS_SIGNATURE_TRUST_ROOTS", "")  # file PEM con le CA dei QTSP
FASAS_CSC_SERVICE_URL = os.environ.get("FASAS_CSC_SERVICE_URL", "")  # URL base delle API CSC del prestatore
FASAS_CSC_API_VERSION = os.environ.get("FASAS_CSC_API_VERSION", "v1")
FASAS_CSC_AUTH = os.environ.get("FASAS_CSC_AUTH", "basic")  # basic | oauth2 | token
FASAS_CSC_OAUTH_TOKEN_URL = os.environ.get("FASAS_CSC_OAUTH_TOKEN_URL", "")
FASAS_CSC_CLIENT_ID = os.environ.get("FASAS_CSC_CLIENT_ID", "")
FASAS_CSC_CLIENT_SECRET = os.environ.get("FASAS_CSC_CLIENT_SECRET", "")
FASAS_CSC_OAUTH_SCOPE = os.environ.get("FASAS_CSC_OAUTH_SCOPE", "service")
FASAS_CSC_TOKEN = os.environ.get("FASAS_CSC_TOKEN", "")
FASAS_CSC_TIMEOUT = int(os.environ.get("FASAS_CSC_TIMEOUT", "30"))
FASAS_CSC_PROVIDER_NAME = os.environ.get("FASAS_CSC_PROVIDER_NAME", "")  # nome mostrato ai medici, es. «InfoCert»

# Firma con CIE (firma elettronica avanzata, FASAS Signer). Vedi docs/FIRMA_CIE.md.
FASAS_CIE_ENABLED = env_bool("FASAS_CIE_ENABLED", True)
FASAS_CIE_TRUST_ROOTS = os.environ.get("FASAS_CIE_TRUST_ROOTS", "")  # PEM con le CA della CIE (Ministero dell'Interno)
FASAS_CIE_INTERMEDIATES = os.environ.get("FASAS_CIE_INTERMEDIATES", "")  # PEM con eventuali CA intermedie
FASAS_CIE_REVOCATION = os.environ.get("FASAS_CIE_REVOCATION", "soft-fail")  # soft-fail | hard-fail | off
FASAS_CIE_TIMESTAMP = env_bool("FASAS_CIE_TIMESTAMP", True)  # marca temporale se è configurata una TSA reale
FASAS_CIE_REQUEST_MINUTES = int(os.environ.get("FASAS_CIE_REQUEST_MINUTES", "5"))
FASAS_CIE_PAIRING_MINUTES = int(os.environ.get("FASAS_CIE_PAIRING_MINUTES", "10"))
FASAS_CIE_ALLOW_HTTP = env_bool("FASAS_CIE_ALLOW_HTTP", DEBUG)  # solo sviluppo: in produzione il Signer usa HTTPS

# Notifiche push (Web Push). Chiave generata con «manage.py fasas_vapid_keys»; in sviluppo se ne deriva una da SECRET_KEY.
FASAS_VAPID_PRIVATE_KEY = os.environ.get("FASAS_VAPID_PRIVATE_KEY", "")
FASAS_VAPID_SUBJECT = os.environ.get("FASAS_VAPID_SUBJECT", "mailto:amministrazione@fasas.invalid")
FASAS_PUSH_SHOW_DETAILS = env_bool("FASAS_PUSH_SHOW_DETAILS", False)  # titolo e messaggio completi sul telefono
FASAS_PUSH_ASYNC = env_bool("FASAS_PUSH_ASYNC", True)

if DEBUG and not FASAS_ENCRYPTION_KEYS:
    # Chiave fissa SOLO per sviluppo: in produzione la mancanza della chiave è un errore.
    FASAS_ENCRYPTION_KEYS = ["ZGV2LW9ubHktZmFzYXMta2V5LWNoYW5nZS1tZS0wMDA="]
if DEBUG and not FASAS_BACKUP_KEY:
    FASAS_BACKUP_KEY = "ZGV2LW9ubHktYmFja3VwLWtleS1jaGFuZ2UtbWUtMDA="

# --- Email (notifiche) -----------------------------------------------------
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "fasas@localhost")

# --- API REST (base per la futura app mobile) ------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "fasas.api.permissions.ModelPermissions",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# --- Attività pianificate (Celery) -----------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)

# Monitoraggio (docs/MONITORAGGIO.md): dettaglio di /salute/ solo con questo token; spazio minimo su disco
FASAS_HEALTH_TOKEN = os.environ.get("FASAS_HEALTH_TOKEN", "")
FASAS_HEALTH_MIN_FREE_GB = float(os.environ.get("FASAS_HEALTH_MIN_FREE_GB", "5"))
FASAS_ERROR_RECORDING = env_bool("FASAS_ERROR_RECORDING", True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        # registro degli errori nel database, senza messaggi né dati (fasas.core.monitoring)
        "record": {"class": "fasas.core.monitoring.ErrorRecordHandler", "level": "ERROR"},
    },
    "loggers": {
        "fasas": {"handlers": ["console", "record"], "level": os.environ.get("FASAS_LOG_LEVEL", "INFO")},
        "django.request": {"handlers": ["record"], "level": "ERROR"},
        # un certificato non presente tra le CA fidate del server è un esito normale della verifica, non un errore
        "pyhanko": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "pyhanko_certvalidator": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
