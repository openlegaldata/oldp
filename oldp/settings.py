# -*- coding: utf-8 -*-
"""Django settings for OLDP (using django-configurations)"""

import os

from configurations import Configuration, importer, values
from configurations import importer
from django.contrib.messages import constants as message_constants
from django.utils.translation import ugettext_lazy as _

from oldp.apps.courts.apps import CourtTypesDefault

importer.install()


class Base(Configuration):
    DEBUG = values.BooleanValue(True)

    # ############# Site Configuration #########

    # Make this unique, and don't share it with anybody.
    SECRET_KEY = 'something_secret'

    SITE_NAME = values.Value('OLDP')
    SITE_EMAIL = values.Value('hello@openlegaldata.io')
    SITE_URL = values.Value('http://localhost:8000')
    SITE_TITLE = values.Value('Open Legal Data')
    SITE_ICON = values.Value('fa-balance-scale')
    SITE_TWITTER_URL = values.Value('https://twitter.com/openlegaldata')
    SITE_GITHUB_URL = values.Value('https://github.com/openlegaldata')
    SITE_BLOG_URL = values.Value('//openlegaldata.io/blog')

    SITE_ID = values.IntegerValue(1)

    INTERNAL_IPS = values.TupleValue(('127.0.0.1',))

    # Set like this: DJANGO_ALLOWED_HOSTS=foo.com,bar.net
    ALLOWED_HOSTS = values.ListValue([
        '127.0.0.1',
        'localhost',
        'oldp.local',
        'de.oldp.local'
    ])

    ####################

    INSTALLED_APPS = [
        # local apps
        'oldp.apps.accounts.apps.AccountsConfig',
        'oldp.apps.laws.apps.LawsConfig',
        'oldp.apps.homepage.apps.HomepageConfig',
        'oldp.apps.cases.apps.CasesConfig',
        'oldp.apps.topics.apps.TopicsConfig',
        'oldp.apps.processing.apps.ProcessingConfig',
        'oldp.apps.search.apps.SearchConfig',
        'oldp.apps.courts.apps.CourtsConfig',
        'oldp.apps.references.apps.ReferencesConfig',
        'oldp.apps.contact.apps.ContactConfig',
        'oldp.apps.annotations.apps.AnnotationsConfig',
        'oldp.apps.sources.apps.SourcesConfig',
        'oldp.apps.lib.apps.LibConfig',

        # third party apps
        'dal',
        'dal_select2',
        'haystack',
        'ckeditor',
        'drf_yasg',
        'rest_framework',
        'rest_framework.authtoken',
        'django_filters',

        # 'envelope',  # contact form
        'tellme',  # feedback
        'widget_tweaks',  # forms
        'crispy_forms',
        'mathfilters',  # math filters for templates
        'bootstrapform',
        'allauth',
        'allauth.account',
        'allauth.socialaccount',
        # 'allauth.socialaccount.providers.google',
        # 'allauth.socialaccount.providers.github',
        # 'allauth.socialaccount.providers.twitter',

        # django internal
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.sites',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'django.contrib.flatpages',
        'django.contrib.sitemaps',
    ]

    # ############## PATHS ###############

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    APPS_DIR = os.path.join(BASE_DIR, 'oldp/apps')
    ASSETS_DIR = os.path.join(BASE_DIR, 'oldp/assets')
    WORKING_DIR = os.path.join(BASE_DIR, 'workingdir')

    # Email settings
    DEFAULT_FROM_EMAIL = values.Value('no-reply@openlegaldata.io')
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = values.Value('localhost')
    EMAIL_PORT = values.IntegerValue(25)
    EMAIL_USE_TLS = values.BooleanValue(False)
    EMAIL_HOST_USER = values.Value('')
    EMAIL_HOST_PASSWORD = values.Value('')

    MIDDLEWARE = [
        # Simplified static file serving.
        # https://warehouse.python.org/project/whitenoise/
        'whitenoise.middleware.WhiteNoiseMiddleware',

        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',

        'django.middleware.locale.LocaleMiddleware',

        'oldp.apps.lib.apps.DomainLocaleMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',

        # 'django.middleware.gzip.GZipMiddleware',
        # 'pipeline.middleware.MinifyHTMLMiddleware',

    ]

    ROOT_URLCONF = 'oldp.urls'

    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [
                os.path.join(BASE_DIR, 'oldp/assets/templates')
            ],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                    'oldp.apps.lib.context_processors.global_context_processor'
                ],
            },
        },
    ]

    WSGI_APPLICATION = 'oldp.wsgi.application'

    # Messages

    MESSAGE_LEVEL = message_constants.DEBUG
    MESSAGE_TAGS = {
        message_constants.DEBUG: 'alert-info',
        message_constants.INFO: 'alert-info',
        message_constants.SUCCESS: 'alert-success',
        message_constants.WARNING: 'alert-warning',
        message_constants.ERROR: 'alert-danger',
    }

    # Password validation
    # https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

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

    AUTHENTICATION_BACKENDS = (
        # Needed to login by username in Django admin, regardless of `allauth`
        'django.contrib.auth.backends.ModelBackend',

        # `allauth` specific authentication methods, such as login by e-mail
        'allauth.account.auth_backends.AuthenticationBackend',
    )

    LOGIN_REDIRECT_URL = '/accounts/email/'
    ACCOUNT_EMAIL_REQUIRED = True
    ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
    ACCOUNT_USERNAME_BLACKLIST = ['admin', 'oldp', 'openlegaldata']
    ACCOUNT_USERNAME_MIN_LENGTH = 3

    # Internationalization
    # https://docs.djangoproject.com/en/1.11/topics/i18n/

    # Select language based on domain
    # https://7webpages.com/blog/switch-language-regarding-of-domain-in-django/

    # Set like this: DJANGO_LANGUAGES_DOMAINS="{'de.foo.com':'de','fr.foo.com':'fr'}"
    LANGUAGES_DOMAINS = values.DictValue({
        'localhost:8000': 'en',
        'oldp.local:8000': 'en',
        'de.oldp.local:8000': 'de',
        '127.0.0.1:8000': 'de',
    })

    LANGUAGE_CODE = 'en'

    @property
    def LANGUAGES(self):
        return (
            ('en', _('English')),
            ('de', _('German')),
        )

    LOCALE_PATHS = (
        os.path.join(BASE_DIR, 'oldp/locale'),
    )

    TIME_ZONE = values.Value('UTC')

    USE_I18N = True

    USE_L10N = True

    USE_TZ = True

    PAGINATE_BY = 50  # Items per page

    PAGINATE_UNTIL = 20  # Max. number of pages

    DATABASES = values.DatabaseURLValue('mysql://oldp:oldp@127.0.0.1/oldp')

    # Caching

    # Cache time to live is 15 minutes.
    CACHE_DISABLE = values.BooleanValue(False)
    CACHE_TTL = values.IntegerValue(60 * 15)

    CACHES = {
        "default": {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': values.Value('redis://127.0.0.1:6379/1', environ_name='REDIS_URL'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient'
            },
        }
    }

    # Honor the 'X-Forwarded-Proto' header for request.is_secure()
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # Static files (CSS, JavaScript, Images)
    # https://docs.djangoproject.com/en/1.9/howto/static-files/
    STATIC_ROOT = os.path.join(BASE_DIR, 'oldp/assets/static-dist')
    STATIC_URL = '/static/'

    STATICFILES_FINDERS = (
        'django.contrib.staticfiles.finders.FileSystemFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    )

    # Extra places for collectstatic to find static files.
    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'oldp/assets/static')
    ]

    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
    MEDIA_URL = '/media/'

    # Simplified static file serving.
    # https://warehouse.python.org/project/whitenoise/

    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

    # Tellme feedback
    TELLME_FEEDBACK_EMAIL = values.Value('hello@openlegaldata.io', environ_name='FEEDBACK_EMAIL')

    # CKEditor (wysiwyg)
    CKEDITOR_BASEPATH = '/static/ckeditor/ckeditor/'

    CKEDITOR_CONFIGS = {
        'default': {
            'allowedContent': True,
            # 'skin': 'kama',
            # 'skin': 'oldp',
            'contentsCss': [
                CKEDITOR_BASEPATH + 'contents.css',
                CKEDITOR_BASEPATH + 'oldp_contents.css'
            ]
        },
    }

    # Elasticsearch
    ELASTICSEARCH_URL = values.Value('http://localhost:9200/', environ_name='ELASTICSEARCH_URL')
    ELASTICSEARCH_INDEX = values.Value('oldp', environ_name='ELASTICSEARCH_INDEX')

    HAYSTACK_CONNECTIONS = {
        'default': {
            'ENGINE': 'oldp.apps.search.search_backend.SearchEngine',
            'URL': values.Value('http://localhost:9200/', environ_name='ELASTICSEARCH_URL'),
            'INDEX_NAME': values.Value('oldp', environ_name='ELASTICSEARCH_INDEX'),
        },
    }
    # HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'

    # Logging
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'console': {
                'format': '%(asctime)s %(levelname)-8s %(name)-12s %(message)s',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'console',
            },
            'logfile': {
                'level': 'DEBUG',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(BASE_DIR, 'logs', 'oldp.log'),
                'maxBytes': 1024*1024*15,  # 15MB
                'backupCount': 10,
                'formatter': 'console',
            },

            # Add Handler for Sentry for `warning` and above
            # 'sentry': {
            #     'level': 'WARNING',
            #     'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
            # },
        },
        'loggers': {
            '': {  # root logger
                'level': 'INFO',
                'handlers': ['console', 'logfile'],
            },
            'oldp': {
                'level': 'DEBUG',
            },
            'refex': {
                'level': 'DEBUG',
            },
            'requests': {
                'level': 'ERROR'
            },
            'elasticsearch': {
                'level': 'ERROR'
            }
        },
    }

    #########################
    # Test config
    #########################

    # Set false to exclude specific tests from test suite
    # TEST_MYSQL = False  # auto detection based on DB settings
    TEST_WITH_ES = values.BooleanValue(True)
    TEST_WITH_WEB = values.BooleanValue(True)
    TEST_WITH_SELENIUM = values.BooleanValue(False)

    ########################
    # Rest API framework
    ########################

    REST_FRAMEWORK = {
        # Use Django's standard `django.contrib.auth` permissions,
        # or allow read-only access for unauthenticated users.
        'DEFAULT_PERMISSION_CLASSES': [
            'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
        ],
        'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
        'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
        'PAGE_SIZE': 50,
        'DEFAULT_RENDERER_CLASSES': (
            'rest_framework.renderers.JSONRenderer',
            'rest_framework.renderers.BrowsableAPIRenderer',
            'rest_framework_xml.renderers.XMLRenderer',
        ),
        # Auth
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework.authentication.TokenAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ),

        'DEFAULT_THROTTLE_CLASSES': (
            'rest_framework.throttling.AnonRateThrottle',
        ),
        'DEFAULT_THROTTLE_RATES': {
            'anon': '100/day',
            'user': '5000/hour',
        },
        'EXCEPTION_HANDLER': 'oldp.api.exceptions.full_details_exception_handler',
    }

    SWAGGER_SETTINGS = {
        'SECURITY_DEFINITIONS': {
            'api_key': {
                'type': 'apiKey',
                'in': 'header',
                'name': 'Authorization'
            }
        },
    }

    # Processing pipeline
    PROCESSING_STEPS = {
        'Case': [
            'oldp.apps.cases.processing.processing_steps.assign_court',
            'oldp.apps.cases.processing.processing_steps.extract_refs',
            'oldp.apps.cases.processing.processing_steps.generate_related',
            'oldp.apps.cases.processing.processing_steps.set_private_true',
            'oldp.apps.cases.processing.processing_steps.set_private_false',
        ],
        'Law': [
            'oldp.apps.laws.processing.processing_steps.extract_refs',
        ],
        'LawBook': [
            'oldp.apps.topics.processing.processing_steps.assign_topics_to_law_book',
        ],
        'Court': [
            'oldp.apps.courts.processing.processing_steps.enrich_from_wikipedia',
            'oldp.apps.courts.processing.processing_steps.set_aliases',
            'oldp.apps.courts.processing.processing_steps.assign_jurisdiction',
        ],
        'Reference': [
            'oldp.apps.references.processing.processing_steps.assign_refs',
        ]
    }

    # Courts
    COURT_JURISDICTIONS = {}
    COURT_LEVELS_OF_APPEAL = {}
    COURT_TYPES = CourtTypesDefault()

    #######################
    # Setup methods
    #######################

    @classmethod
    def post_setup(cls):
        """Check database setup after settings are loaded"""
        # super(Base, cls).post_setup()

        if cls.DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
            # Force strict mode (MySQL only)
            # https://stackoverflow.com/questions/23022858/force-strict-sql-mode-in-django
            if 'OPTIONS' not in cls.DATABASES['default']:
                cls.DATABASES['default']['OPTIONS'] = {}

            cls.DATABASES['default']['OPTIONS']['sql_mode'] = 'traditional'
            # TODO Check this to handle "Incorrect string value" db error
            # cls.DATABASES['default']['OPTIONS']['charset'] = 'utf8mb4'

            cls.DATABASE_MYSQL = True
        else:
            cls.DATABASE_MYSQL = False

        # Disable cache
        if cls.DEBUG and cls.CACHE_DISABLE:
            cls.CACHES['default']['BACKEND'] = 'django.core.cache.backends.dummy.DummyCache'

        # Overwrite log filename
        log_file = values.Value(default=None, environ_name='LOG_FILE')

        if 'handlers' in cls.LOGGING and 'logfile' in cls.LOGGING['handlers'] and log_file:
            cls.LOGGING['handlers']['logfile']['filename'] = os.path.join(cls.BASE_DIR, 'logs', log_file)


class Dev(Base):
    """Development settings (debugging enabled)"""
    DEBUG = True


    @property
    def INSTALLED_APPS(self):
        """Apps that are only available in debug mode"""
        return [
            'django_extensions',  # from generating UML chart

        ] + super().INSTALLED_APPS + [
            'debug_toolbar',
        ]

    @property
    def MIDDLEWARE(self):
        """Middlewares that are only available in debug mode"""
        return super().MIDDLEWARE + [
            'debug_toolbar.middleware.DebugToolbarMiddleware'
        ]


class Test(Base):
    """Use these settings for unit testing"""
    DEBUG = True

    DATABASES = values.DatabaseURLValue('sqlite:///test.db')
    ELASTICSEARCH_INDEX = values.Value('oldp_test')

    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

    CACHE_DISABLE = True


class Prod(Base):
    """Production settings (override default values with environment vars"""
    SECRET_KEY = values.SecretValue()

    DEBUG = False

    # Set like this: DJANGO_ADMINS=Foo,foo@site.com;Bar,bar@site.com
    ADMINS = values.SingleNestedTupleValue()
