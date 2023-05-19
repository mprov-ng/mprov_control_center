"""
Django settings for mprov_control_center project.

Generated by 'django-admin startproject' using Django 2.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/
"""

import os
import ldap
from django_auth_ldap.config import LDAPSearch, PosixGroupType

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# default to an empty string, set this in the .env file!
SECRET_KEY = os.environ.get('SECRET_KEY', '')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = str(os.environ.get('DEBUG')) == "1"

ALLOWED_HOSTS = ['127.0.0.1','localhost']
ALLOWED_HOSTS += os.environ.get('ALLOWED_HOSTS', '').split(',')

# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django_filters',
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    'networks',
    'osmanagement',
    'systems',
    'jobqueue',
    'scripts',
    'disklayouts',
    'rest_framework',
    'rest_framework_api_key',
    'dbbackup',
    'utils',
]
DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': '/var/www/mprov_control_center/backups/'}
JAZZMIN_SETTINGS={
    'show_ui_builder': True,
    'site_logo': 'mProvLogo.png',
    'icons': {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        'systems.systemgroup': 'fas fa-sitemap',
        'systems.system': 'fas fa-hdd',
        'systems': 'fas fa-hdd',
        'osmanagement.osrepo': 'fas fa-archive',
        'osmanagement.osdistro': 'fas fa-compact-disc',
        'osmanagement': 'fas fa-compact-disc',
        'networks.switch': 'fas fa-server',
        'networks.network': 'fas fa-network-wired',
        'networks.networktype': 'fas fa-project-diagram',
        'networks': 'fas fa-project-diagram',
        'jobqueue.job':'fas fa-business-time',
        'jobqueue':'fas fa-business-time',
        'jobqueue.jobmodule':'fas fa-search-plus',
        'jobqueue.jobserver':'fas fa-hdd',
        'systems.systemimage': 'fas fa-save',
        'rest_framework_api_key.apikey': 'fas fa-key',
        'rest_framework_api_key': 'fas fa-key',
        'scripts.script': 'fas fa-scroll',
        'scripts': 'fas fa-scroll',
        'systems.systemmodel': 'far fa-object-group',
        'disklayouts.disklayout': 'fas fa-chart-pie',
        'disklayouts.raidlayout': 'fas fa-database',
        'disklayouts': 'fas fa-save',
        'scripts.ansibleplaybook': 'fas fa-clipboard-list',
        'scripts.ansiblerole': 'fas fa-tags',
        'scripts.ansiblecollection': 'far fa-object-group',
    },
    'copyright': ' 2022 The Johns Hopkins University ',
    "related_modal_active": False,
    "navigation_expanded": False,

}
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": True,
    "brand_small_text": False,
    "brand_colour": "navbar-teal",
    "accent": "accent-primary",
    "navbar": "navbar-teal navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-light-olive",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "minty",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": False
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django_session_timeout.middleware.SessionTimeoutMiddleware',   
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
SESSION_EXPIRE_SECONDS = float(os.environ.get('SESSION_EXPIRE_SECONDS', '1800'))
SESSION_TIMEOUT_REDIRECT = '/admin/login/'
SESSION_EXPIRE_AFTER_LAST_ACTIVITY = True
ROOT_URLCONF = 'mprov_control_center.urls'
TIME_ZONE = os.environ.get('TIME_ZONE', 'UTC')
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates/')],
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

WSGI_APPLICATION = 'mprov_control_center.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.environ.get('DB_NAME', os.path.join(BASE_DIR, 'db/db.sqlite3')),
        'USER': os.environ.get("DB_USER", ''),
        'PASSWORD': os.environ.get("DB_PASS", ''),
        'HOST': os.environ.get("DB_HOST", ''),
        'PORT': os.environ.get("DB_PORT", ''),
    }
}


# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

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

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
        'rest_framework_api_key.permissions.HasAPIKey',
    ),   
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend']
}


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = os.environ.get('TIME_ZONE', 'UTC')

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/
STATIC_ROOT = os.path.join(BASE_DIR,"static")
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'common/static/')
]
#    os.path.join(BASE_DIR,"static"),
    #'/var/www/static/',
#]

MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "media/"

CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '127.0.0.1:11211',
    }
}

# LDAP OPTIONS:
if os.environ.get("LDAP_ENABLED", "0") == "1":

    # Most of these should be configurable via the .enf file.  Please read carefully to see if you need to adjust anything.
    # You can also see the docs for the LDAP python module for django here: https://django-auth-ldap.readthedocs.io
    AUTH_LDAP_SERVER_URI = os.environ.get("LDAP_URI", '')

    # The base to use for searches below.
    AUTH_MPROV_LDAP_BASE = os.environ.get("LDAP_BASE", "dc=example,dc=com")

    # If you are not using direct binds, this is a user and pass that can read authentication
    # for you.
    #AUTH_LDAP_BIND_DN = os.environ.get("LDAP_BINDDN", '')
    #AUTH_LDAP_BIND_PASSWORD = os.environ.get("LDAP_BINDPASS", '')

    # Used in non-direct binds to find users.
    # This can be overridden with hard coded unions.  See https://django-auth-ldap.readthedocs.io/en/latest/authentication.html
    #AUTH_LDAP_USER_SEARCH = LDAPSearch(os.environ.get("LDAP_USER_SEARCH", "ou=users,dc=example,dc=com"), ldap.SCOPE_SUBTREE, "(uid=%(user)s)")

    # Here, we will be binding directly.  This is the template to use to look for users to authenticate.

    AUTH_LDAP_USER_DN_TEMPLATE = os.environ.get("LDAP_USER_DN_TEMPLATE", f"uid=%(user)s,ou=users,{AUTH_MPROV_LDAP_BASE}")

    # the group you MUST be a member of to get access to the system.
    AUTH_LDAP_REQUIRE_GROUP = os.environ.get("LDAP_ADMIN_GROUP", "")

    # if LDAP is enabled, set up LDAP as the first backend.    
    AUTHENTICATION_BACKENDS = [
        "django_auth_ldap.backend.LDAPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]

    # place any other defaults here.
    AUTH_LDAP_GLOBAL_OPTIONS={}
    # set if LDAP_SELF_SIGNED_CERT is set in the env.

    if os.environ.get("LDAP_SELF_SIGNED_CERT", "0") == "1":
        AUTH_LDAP_GLOBAL_OPTIONS = AUTH_LDAP_GLOBAL_OPTIONS.update({ ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_NEVER })


    # You may need to change this depending on your LDAP setup.  If you change this, make sure
    # you import the right Type from the module at the top of this file.
    AUTH_LDAP_GROUP_TYPE = PosixGroupType(name_attr="cn")
    AUTH_LDAP_GROUP_SEARCH = LDAPSearch({AUTH_MPROV_LDAP_BASE},ldap.SCOPE_SUBTREE, "(objectClass=posixGroup)")


    AUTH_LDAP_USER_FLAGS_BY_GROUP = {
        "is_staff": os.environ.get("LDAP_STAFF_GROUP", "cn=staff,ou=Group,dc=example,dc=com"),
        "is_superuser": os.environ.get("LDAP_SUPER_GROUP", "cn=wheel,ou=Group,dc=example,dc=com")
    }

    # modify this map to fit your LDAP
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "cn",
        "last_name": "sn",
        "email": "mail",
    }

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"console": {"class": "logging.StreamHandler"}},
        "loggers": {"django_auth_ldap": {"level": "DEBUG", "handlers": ["console"]}},
    }
