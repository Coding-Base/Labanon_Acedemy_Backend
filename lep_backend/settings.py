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
    'whitenoise.middleware.WhiteNoiseMiddleware',
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
    'https://lighthubacademy.cloud',
    'https://api.lighthubacademy.cloud',
    'https://encoder.lighthubacademy.cloud',
]

env_cors = os.environ.get('CORS_ALLOWED_ORIGINS')
if env_cors:
    CORS_ALLOWED_ORIGINS.extend(env_cors.split(','))

CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173').split(',')

# ==================== Email ====================
ANYMAIL = {
    "MAILJET_API_KEY": os.environ.get('MAILJET_API_KEY'),
    "MAILJET_SECRET_KEY": os.environ.get('MAILJET_SECRET_KEY'),
}
if ANYMAIL["MAILJET_API_KEY"] and ANYMAIL["MAILJET_SECRET_KEY"]:
    EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = 'LightHub Academy <lighthub18@gmail.com>'
SERVER_EMAIL = 'lighthub18@gmail.com'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'lighthub18@gmail.com')

# Invite code used to allow registration of master admin accounts
ADMIN_INVITE_CODE = os.environ.get('ADMIN_INVITE_CODE')
if ADMIN_INVITE_CODE:
    ADMIN_INVITE_CODE = ADMIN_INVITE_CODE.strip() or None

# Frontend base URL used in emails and password reset links
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://lighthubacademy.cloud')
if FRONTEND_URL:
    FRONTEND_URL = FRONTEND_URL.strip()


# ==================== DRF & Djoser ====================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

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
# NOTE: AWS S3 is used ONLY for videos, not for general media files like images
# Videos use explicit VideoS3Storage class in views/serializers
# General media uses DEFAULT_FILE_STORAGE (Cloudinary or Filesystem)

if USE_AWS_S3:
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    
    CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
    CLOUDFRONT_DISTRIBUTION_ID = os.environ.get('CLOUDFRONT_DISTRIBUTION_ID')
    CLOUDFRONT_KEY_PAIR_ID = os.environ.get('CLOUDFRONT_KEY_PAIR_ID')

    CLOUDFRONT_KEY_CONTENT = os.environ.get('CLOUDFRONT_PRIVATE_KEY_CONTENT')
    CLOUDFRONT_KEY_PATH_ENV = os.environ.get('CLOUDFRONT_PRIVATE_KEY_PATH')
    
    # Priority order for PEM key:
    # 1. Look for file in project directory (included in git repo)
    # 2. Look for file at /etc/cloudfront/ path (if added via Dokploy files)
    # 3. Create from environment variable if provided
    # 4. Use path from environment variable
    
    # Check project directory first (useful for both dev and production)
    project_key_path = BASE_DIR / 'cloudfront_private_key.pem'
    standard_key_path = '/etc/cloudfront/private-key.pem'
    
    if os.path.exists(project_key_path):
        CLOUDFRONT_PRIVATE_KEY_PATH = str(project_key_path)
    elif os.path.exists(standard_key_path):
        CLOUDFRONT_PRIVATE_KEY_PATH = standard_key_path
    elif CLOUDFRONT_KEY_CONTENT:
        # --- ROBUST KEY CLEANING START ---
        key_content = CLOUDFRONT_KEY_CONTENT.strip()

        # 1. Remove surrounding quotes (common .env paste error)
        if key_content.startswith('"') and key_content.endswith('"'):
            key_content = key_content[1:-1]
        elif key_content.startswith("'") and key_content.endswith("'"):
            key_content = key_content[1:-1]

        # 2. Convert literal escaped newlines (e.g. \n string) to actual newlines
        key_content = key_content.replace('\\n', '\n')

        # 3. Ensure proper spacing for headers (fix potential copy-paste errors)
        key_content = key_content.replace('----- BEGIN', '-----BEGIN')
        key_content = key_content.replace('----- END', '-----END')

        # 4. Write to temp file in Text Mode ('w')
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem') as key_file:
            key_file.write(key_content)
            # Ensure file ends with a newline (PEM requirement)
            if not key_content.endswith('\n'):
                key_file.write('\n')
            CLOUDFRONT_PRIVATE_KEY_PATH = key_file.name
        # --- ROBUST KEY CLEANING END ---

    elif CLOUDFRONT_KEY_PATH_ENV:
        # Use file path directly from environment
        CLOUDFRONT_PRIVATE_KEY_PATH = CLOUDFRONT_KEY_PATH_ENV
    else:
        CLOUDFRONT_PRIVATE_KEY_PATH = None
    
    CLOUDFRONT_ORIGIN_SECRET = os.environ.get('CLOUDFRONT_ORIGIN_SECRET')
    CLOUDFRONT_CUSTOM_AUTH_SECRET = os.environ.get('CLOUDFRONT_CUSTOM_AUTH_SECRET')
    
    AWS_S3_CUSTOM_DOMAIN = f"{CLOUDFRONT_DOMAIN}"
    AWS_LOCATION = 'media'
    # Video uploads will use the CloudFront domain
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