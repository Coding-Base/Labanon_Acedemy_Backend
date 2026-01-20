import os
import tempfile  # Added for CloudFront key handling
import dj_database_url  # Added for Database handling
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from backend .env (development convenience)
load_dotenv(BASE_DIR / '.env')

# Minimal settings for local development
SECRET_KEY = os.environ.get('DJ_SECRET', 'change-me-for-prod')
DEBUG = os.environ.get('DJ_DEBUG', 'True').lower() in ('1', 'true', 'yes')

# ==================== Allowed Hosts ====================
# In production, this splits the comma-separated list from Dokploy
ALLOWED_HOSTS = ['*'] if DEBUG else os.environ.get('ALLOWED_HOSTS', '').split(',')


# Frontend URL for Password Resets & Email Links
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173').rstrip('/')

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
    'anymail',  # Added for Mailjet support
    # cloudinary apps are optional and used only when USE_CLOUDINARY=True
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

# filter out None if cloudinary not used
INSTALLED_APPS = [a for a in INSTALLED_APPS if a]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Recommended for static files in Prod
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'lep_backend.middleware.CloudFrontOriginMiddleware',
]

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

# ==================== Database Configuration ====================
# Checks for DATABASE_URL env var (Dokploy). If not found, uses SQLite (Local).
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600
    )
}

# ==================== Redis Configuration ====================
# Uses the REDIS_URL from Dokploy (redis://lighthub-redis:6379/0)
REDIS_URL = os.environ.get('REDIS_URL')

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
    # Fallback to local memory if no Redis
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }


AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' # Required for production collection

# Media settings
MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media'))

# Site base (used to build absolute URLs when request context is missing)
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000').rstrip('/')

# Storage backend toggled by environment variable USE_CLOUDINARY
USE_CLOUDINARY = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
if USE_CLOUDINARY:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
else:
    # local filesystem for development
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# ==================== CORS & CSRF Settings ====================
CORS_ALLOW_ALL_ORIGINS = False

# Combine local dev URL with any production URLs provided in env
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:3000',
    'https://lighthubacademy.cloud',
    'https://api.lighthubacademy.cloud',
    'https://encoder.lighthubacademy.cloud',
]

# If CORS_ALLOWED_ORIGINS is passed in Env, append them
env_cors = os.environ.get('CORS_ALLOWED_ORIGINS')
if env_cors:
    CORS_ALLOWED_ORIGINS.extend(env_cors.split(','))

# CRITICAL for production HTTPS (Traefik Proxy)
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173').split(',')


# ==================== Email Configuration (Mailjet via Anymail) ====================
# Requires "django-anymail[mailjet]" to be installed
ANYMAIL = {
    "MAILJET_API_KEY": os.environ.get('MAILJET_API_KEY'),
    "MAILJET_SECRET_KEY": os.environ.get('MAILJET_SECRET_KEY'),
}

if ANYMAIL["MAILJET_API_KEY"] and ANYMAIL["MAILJET_SECRET_KEY"]:
    EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"
else:
    # Fallback to console backend for development if keys are missing
    # Emails will print to terminal instead of sending
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = 'LightHub Academy <lighthub18@gmail.com>'
SERVER_EMAIL = 'lighthub18@gmail.com'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'lighthub18@gmail.com')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

# Djoser settings for activation & password reset flows
DJOSER = {
    'USER_ID_FIELD': 'id',
    'LOGIN_FIELD': 'username',
    # For development convenience we disable required activation so users can login
    'SEND_ACTIVATION_EMAIL': False,
    'ACTIVATION_URL': 'activate/{uid}/{token}',
    'PASSWORD_RESET_CONFIRM_URL': 'reset-password/{uid}/{token}', 
    'SERIALIZERS': {
        'user_create': 'users.serializers.DjoserUserCreateSerializer',
    }
}

# Platform commission percentage (e.g., 0.05 = 5%)
PLATFORM_COMMISSION = float(os.environ.get('PLATFORM_COMMISSION', 0.05))

# Admin invite code (optional)
ADMIN_INVITE_CODE = os.environ.get('ADMIN_INVITE_CODE')

AUTH_USER_MODEL = 'users.User'

# ==================== Authentication Backends ====================
AUTHENTICATION_BACKENDS = [
    'users.backends.EmailOrUsernameModelBackend', 
    'django.contrib.auth.backends.ModelBackend',
]

# ==================== AWS S3 + CloudFront Configuration ====================
USE_AWS_S3 = os.environ.get('USE_AWS_S3', 'False').lower() in ('1', 'true', 'yes')

if USE_AWS_S3:
    # AWS S3 Credentials
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    
    # CloudFront Configuration
    CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
    CLOUDFRONT_DISTRIBUTION_ID = os.environ.get('CLOUDFRONT_DISTRIBUTION_ID')
    CLOUDFRONT_KEY_PAIR_ID = os.environ.get('CLOUDFRONT_KEY_PAIR_ID')

    # --- CLOUDFRONT KEY LOGIC (UPDATED FOR DOKPLOY) ---
    # 1. Try to get the raw content (Production Env Var)
    CLOUDFRONT_KEY_CONTENT = os.environ.get('CLOUDFRONT_PRIVATE_KEY_CONTENT')
    # 2. Try to get the local path (Development .env)
    CLOUDFRONT_KEY_PATH_DEV = os.environ.get('CLOUDFRONT_PRIVATE_KEY_PATH')

    if CLOUDFRONT_KEY_CONTENT:
        # PRODUCTION: Write content to a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as key_file:
            key_file.write(CLOUDFRONT_KEY_CONTENT)
            CLOUDFRONT_PRIVATE_KEY_PATH = key_file.name
    else:
        # DEVELOPMENT: Use the file path
        CLOUDFRONT_PRIVATE_KEY_PATH = CLOUDFRONT_KEY_PATH_DEV
    # --------------------------------------------------
    
    # CloudFront Custom Headers for Security
    CLOUDFRONT_ORIGIN_SECRET = os.environ.get('CLOUDFRONT_ORIGIN_SECRET')
    CLOUDFRONT_CUSTOM_AUTH_SECRET = os.environ.get('CLOUDFRONT_CUSTOM_AUTH_SECRET')
    
    # S3 Storage Settings
    AWS_S3_CUSTOM_DOMAIN = f"{CLOUDFRONT_DOMAIN}"
    AWS_LOCATION = 'media'
    
    # Use CloudFront URLs for all media files
    MEDIA_URL = f"https://{CLOUDFRONT_DOMAIN}/{AWS_LOCATION}/"
    
    # Default storage backend for file uploads
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    
    AWS_S3_DEFAULT_SSE = os.getenv('AWS_S3_DEFAULT_SSE', 'AES256')
else:
    # Fallback to local filesystem
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    CLOUDFRONT_DOMAIN = None
    CLOUDFRONT_DISTRIBUTION_ID = None
    CLOUDFRONT_KEY_PAIR_ID = None
    CLOUDFRONT_PRIVATE_KEY_PATH = None
    CLOUDFRONT_ORIGIN_SECRET = None
    CLOUDFRONT_CUSTOM_AUTH_SECRET = None

# ==================== Payment Gateway Configuration ====================
# Paystack Configuration
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY')

# Flutterwave Configuration
FLUTTERWAVE_SECRET_KEY = os.environ.get('FLUTTERWAVE_SECRET_KEY')
FLUTTERWAVE_PUBLIC_KEY = os.environ.get('FLUTTERWAVE_PUBLIC_KEY')
FLUTTERWAVE_ENCRYPTION_KEY = os.environ.get('FLUTTERWAVE_ENCRYPTION_KEY')