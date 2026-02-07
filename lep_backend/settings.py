import os
import tempfile
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / '.env')

# Security settings
SECRET_KEY = os.environ.get('DJ_SECRET', 'change-me-for-prod')
DEBUG = os.environ.get('DJ_DEBUG', 'True').lower() in ('1', 'true', 'yes')

# ALLOWED_HOSTS: Handling comma-separated string from Env
ALLOWED_HOSTS = ['*'] if DEBUG else os.environ.get('ALLOWED_HOSTS', '').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'djoser',
    'anymail',
    'cloudinary' if os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes') else None,
    'cloudinary_storage' if os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes') else None,
    'users',
    'courses',
    'cbt',
    'videos',
    'blog',
    'subadmin',
    'messaging',
]
INSTALLED_APPS = [a for a in INSTALLED_APPS if a]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'lep_backend.middleware.rate_limit.RateLimitMiddleware',
    'lep_backend.middleware.security_headers.SecurityHeadersMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'lep_backend.middleware.CloudFrontOriginMiddleware',
]

# === Security hardening defaults ===
# Enable secure cookies in production
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Prevent content sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True
# Enable browser XSS filter
SECURE_BROWSER_XSS_FILTER = True
# Prevent the site from being framed to avoid clickjacking
X_FRAME_OPTIONS = 'DENY'

# HSTS - only enable when running over HTTPS in production
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# Force HTTPS redirect in production
SECURE_SSL_REDIRECT = not DEBUG

# Referrer policy
SECURE_REFERRER_POLICY = 'no-referrer-when-downgrade'

# Rate limiting (middleware) defaults - IP based protection
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get('RATE_LIMIT_MAX_REQUESTS', '300'))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('RATE_LIMIT_WINDOW_SECONDS', '300'))
RATE_LIMIT_BAN_SECONDS = int(os.environ.get('RATE_LIMIT_BAN_SECONDS', '600'))


ROOT_URLCONF = 'lep_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lep_backend.wsgi.application'

# ==================== Database ====================
# This automatically picks up the "DATABASE_URL" from Dokploy
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ==================== Redis & Celery ====================
# This will now pick up the full connection string from Dokploy
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Configure Celery to use the Redis URL
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Configure Django Cache to use the Redis URL
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# ==================== Internationalization ====================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ==================== Static & Media ====================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media'))

# Storage Configuration
# Priority: Cloudinary > Filesystem (S3 is only for videos via explicit storage class)
USE_CLOUDINARY = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
USE_AWS_S3 = os.environ.get('USE_AWS_S3', 'False').lower() in ('1', 'true', 'yes')

# Default storage for general media (images, documents, etc.) - NOT videos
if USE_CLOUDINARY:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# ==================== CORS & CSRF ====================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:3000',
    'https://lighthubacademy.org',
    'https://www.lighthubacademy.org',
    'https://api.lighthubacademy.org',
    'https://encoder.lighthubacademy.org',
]

env_cors = os.environ.get('CORS_ALLOWED_ORIGINS')
if env_cors:
    CORS_ALLOWED_ORIGINS.extend(env_cors.split(','))

# Explicitly add the new domain to CSRF trusted origins to prevent 403 errors on forms
CSRF_TRUSTED_ORIGINS = [
    'https://lighthubacademy.org', 
    'https://www.lighthubacademy.org',
    'https://api.lighthubacademy.org',
    'http://localhost:5173'
]
env_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS')
if env_csrf:
    CSRF_TRUSTED_ORIGINS.extend(env_csrf.split(','))

# ==================== Email ====================
ANYMAIL = {
    "MAILJET_API_KEY": os.environ.get('MAILJET_API_KEY'),
    "MAILJET_SECRET_KEY": os.environ.get('MAILJET_SECRET_KEY'),
}
if ANYMAIL["MAILJET_API_KEY"] and ANYMAIL["MAILJET_SECRET_KEY"]:
    EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# UPDATED: Use the verified domain email for sending to avoid spam
DEFAULT_FROM_EMAIL = 'LightHub Academy <support@lighthubacademy.org>'
SERVER_EMAIL = 'support@lighthubacademy.org'

# UPDATED: Keep your Gmail for receiving admin alerts (if preferred), or change to support@
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'lighthub18@gmail.com')

# Invite code used to allow registration of master admin accounts
ADMIN_INVITE_CODE = os.environ.get('ADMIN_INVITE_CODE')
if ADMIN_INVITE_CODE:
    ADMIN_INVITE_CODE = ADMIN_INVITE_CODE.strip() or None

# Frontend base URL used in emails and password reset links
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://lighthubacademy.org')
if FRONTEND_URL:
    FRONTEND_URL = FRONTEND_URL.strip()


# ==================== DRF & Djoser ====================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

# DRF throttling to protect API endpoints from high request rates
REST_FRAMEWORK.setdefault('DEFAULT_THROTTLE_CLASSES', [
    'rest_framework.throttling.AnonRateThrottle',
    'rest_framework.throttling.UserRateThrottle',
])
REST_FRAMEWORK.setdefault('DEFAULT_THROTTLE_RATES', {
    'anon': os.environ.get('DRF_THROTTLE_ANON', '60/min'),
    'user': os.environ.get('DRF_THROTTLE_USER', '300/min'),
})

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

DJOSER = {
    'USER_ID_FIELD': 'id',
    'LOGIN_FIELD': 'username',
    'SEND_ACTIVATION_EMAIL': False,
    'ACTIVATION_URL': 'activate/{uid}/{token}',
    'PASSWORD_RESET_CONFIRM_URL': 'reset-password/{uid}/{token}',
    'SERIALIZERS': {
        'user_create': 'users.serializers.DjoserUserCreateSerializer',
    }
}

AUTH_USER_MODEL = 'users.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTHENTICATION_BACKENDS = [
    'users.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ==================== AWS CloudFront ====================
if USE_AWS_S3:
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    
    CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
    CLOUDFRONT_DISTRIBUTION_ID = os.environ.get('CLOUDFRONT_DISTRIBUTION_ID')
    CLOUDFRONT_KEY_PAIR_ID = os.environ.get('CLOUDFRONT_KEY_PAIR_ID')

    # Path to the key we generated via Start Command
    # (Generated from CLOUDFRONT_PEM_B64 env var)
    dokploy_generated_key = '/app/cloudfront_key.pem'
    
    # Path inside project (for local dev)
    local_project_key = BASE_DIR / 'cloudfront_private_key.pem'

    # Fallback env var
    env_path = os.environ.get('CLOUDFRONT_PRIVATE_KEY_PATH')

    if os.path.exists(dokploy_generated_key):
        CLOUDFRONT_PRIVATE_KEY_PATH = dokploy_generated_key
    elif os.path.exists(local_project_key):
        CLOUDFRONT_PRIVATE_KEY_PATH = str(local_project_key)
    elif env_path:
        CLOUDFRONT_PRIVATE_KEY_PATH = env_path
    else:
        CLOUDFRONT_PRIVATE_KEY_PATH = None
    
    CLOUDFRONT_ORIGIN_SECRET = os.environ.get('CLOUDFRONT_ORIGIN_SECRET')
    CLOUDFRONT_CUSTOM_AUTH_SECRET = os.environ.get('CLOUDFRONT_CUSTOM_AUTH_SECRET')
    
    AWS_S3_CUSTOM_DOMAIN = f"{CLOUDFRONT_DOMAIN}"
    AWS_LOCATION = 'media'
    AWS_S3_DEFAULT_SSE = os.getenv('AWS_S3_DEFAULT_SSE', 'AES256')
else:
    CLOUDFRONT_DOMAIN = None
    CLOUDFRONT_PRIVATE_KEY_PATH = None

# ==================== Payments ====================
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY')
FLUTTERWAVE_SECRET_KEY = os.environ.get('FLUTTERWAVE_SECRET_KEY')
FLUTTERWAVE_PUBLIC_KEY = os.environ.get('FLUTTERWAVE_PUBLIC_KEY')
FLUTTERWAVE_ENCRYPTION_KEY = os.environ.get('FLUTTERWAVE_ENCRYPTION_KEY')

# ------------------ Google Analytics (GA4) ------------------
# Numeric GA4 property ID (not the G- measurement id). Example: 123456789
GA4_PROPERTY_ID = os.environ.get('GA4_PROPERTY_ID')
# Path where the service account JSON will be written on the server/container.
# We prefer writing this file at container start from a secret env var (hex/base64).
GA_SERVICE_ACCOUNT_FILE = os.environ.get('GA_SERVICE_ACCOUNT_FILE', '/app/ga_service_account.json')

# If the expected GA service-account JSON file does not exist, attempt to
# write it from an environment secret. Prefer hex (`GA_SERVICE_ACCOUNT_HEX`)
# or base64 (`GA_SERVICE_ACCOUNT_JSON`). This helps Dokploy/Docker deployments
# where writing the secret from an env var at container start is easiest.
if GA_SERVICE_ACCOUNT_FILE and not os.path.exists(GA_SERVICE_ACCOUNT_FILE):
    try:
        ga_hex = os.environ.get('GA_SERVICE_ACCOUNT_HEX')
        ga_b64 = os.environ.get('GA_SERVICE_ACCOUNT_JSON') or os.environ.get('GA_SERVICE_ACCOUNT_BASE64')
        if ga_hex:
            import binascii
            with open(GA_SERVICE_ACCOUNT_FILE, 'wb') as f:
                f.write(binascii.unhexlify(ga_hex))
        elif ga_b64:
            import base64
            with open(GA_SERVICE_ACCOUNT_FILE, 'wb') as f:
                f.write(base64.b64decode(ga_b64))
    except Exception as _e:
        # Avoid crashing import-time; log to stderr so deploy logs capture the error
        try:
            import sys
            print(f"Warning: failed to write GA service account file: {_e}", file=sys.stderr)
        except Exception:
            pass