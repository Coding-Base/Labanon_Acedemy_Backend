import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from backend .env (development convenience)
load_dotenv(BASE_DIR / '.env')

# Minimal settings for local development
SECRET_KEY = os.environ.get('DJ_SECRET', 'change-me-for-prod')
DEBUG = True
ALLOWED_HOSTS = ['*']

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
    'cloudinary',
    'cloudinary_storage',
    'users',
    'courses',
    'cbt',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
MEDIA_URL = '/media/'

# Cloudinary storage (use CLOUDINARY_URL env variable)
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# CORS for frontend dev server (Vite default port 5173)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
]

# Email backend for dev — change to SMTP in production
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

# Djoser settings for activation & password reset flows
DJOSER = {
    'USER_ID_FIELD': 'id',
    'LOGIN_FIELD': 'username',
    # For development convenience we disable required activation so users can login
    # immediately. In production you should enable activation (set to True) and
    # configure a real email backend.
    'SEND_ACTIVATION_EMAIL': False,
    'ACTIVATION_URL': 'activate/{uid}/{token}',
    'PASSWORD_RESET_CONFIRM_URL': 'password/reset/confirm/{uid}/{token}',
    'SERIALIZERS': {
        'user_create': 'users.serializers.DjoserUserCreateSerializer',
    }
}

# Platform commission percentage (e.g., 0.05 = 5%)
PLATFORM_COMMISSION = float(os.environ.get('PLATFORM_COMMISSION', 0.05))

# Admin invite code (optional) - read from environment so serializers can validate admin registration
ADMIN_INVITE_CODE = os.environ.get('ADMIN_INVITE_CODE')

AUTH_USER_MODEL = 'users.User'
