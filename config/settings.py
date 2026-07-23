import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'change-me-before-production')

DEBUG = True

ALLOWED_HOSTS = [
    '77.222.55.79',
    'localhost',
    '127.0.0.1',
]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'publisher',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DB_NAME', os.path.join('/app/data', 'db.sqlite3')),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = False

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
# Папка для временных видео
TEMP_VIDEO_DIR = os.path.join(BASE_DIR, 'media', 'temp_videos')

YANDEX_URL = 'https://cloud-api.yandex.net/v1/disk/public/resources' # API Яндекс Диска для публичных ресурсов
GEELARK_API_URL = ''
GEELARK_TOKEN = os.environ.get('GEELARK_TOKEN', '')
GEELARK_PROXY_AUTO_ROTATE = os.environ.get('GEELARK_PROXY_AUTO_ROTATE', '').lower() in {
    '1', 'true', 'yes', 'on'
}
GEELARK_PROXY_PORT_MIN = int(os.environ.get('GEELARK_PROXY_PORT_MIN', '10000'))
GEELARK_PROXY_PORT_MAX = int(os.environ.get('GEELARK_PROXY_PORT_MAX', '10999'))
GEELARK_PROXY_ROTATE_ATTEMPTS = int(os.environ.get('GEELARK_PROXY_ROTATE_ATTEMPTS', '3'))
