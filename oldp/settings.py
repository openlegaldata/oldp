"""Django settings for OLDP (using django-configurations)"""

import os
from pathlib import Path

from configurations import Configuration, values
from configurations.values import Value, setup_value
from django.contrib.messages import constants as message_constants
from django.utils.translation import gettext_lazy as _

from oldp.apps.courts.apps import CourtTypesDefault

# Legal-domain synonym groups for the Elasticsearch ``german_legal``
# analyzer (see ``ELASTICSEARCH_INDEX_SETTINGS``). These cover equivalences
# that stemming alone cannot fold (verified via ES ``_analyze``):
#
#   * Gendered actor roles — the feminine ``-in`` is *derivational*, so no
#     German stemmer reduces ``Vermieterin`` to ``Vermieter`` (it would
#     reduce ``Vermieter`` -> "vermiet" but leave "vermieterin" intact).
#   * Spelling variants — ``Schadenersatz`` / ``Schadensersatz`` differ by
#     the Fugen-s (a *compounding* variant, also invisible to a stemmer).
#
# Each line is a comma-separated equivalence set in lower-case surface form
# (the synonym filter runs after ``lowercase`` but before
# ``german_normalization`` + stemming, so umlauts/ß are written as typed).
# Only pairs that do NOT already co-stem are listed — e.g. adjectival
# ``beklagter``/``beklagte`` both stem to "beklagt" and need no synonym.
# Deliberately conservative: pure referential equivalences only, no broad
# near-synonyms (e.g. Kündigung/Beendigung) that would hurt precision.
LEGAL_SYNONYMS = [
    "schadenersatz, schadensersatz",
    "vermieter, vermieterin",
    "mieter, mieterin",
    "kläger, klägerin",
    "arbeitnehmer, arbeitnehmerin",
    "arbeitgeber, arbeitgeberin",
    "antragsteller, antragstellerin",
    "antragsgegner, antragsgegnerin",
    "käufer, käuferin",
    "verkäufer, verkäuferin",
    "eigentümer, eigentümerin",
    "erbe, erbin",
    "schuldner, schuldnerin",
    "gläubiger, gläubigerin",
    "geschäftsführer, geschäftsführerin",
    "betreuer, betreuerin",
    "zeuge, zeugin",
    "versicherungsnehmer, versicherungsnehmerin",
    "verbraucher, verbraucherin",
]

# Colloquial -> technical concept synonyms (see overview backlog #14).
# Laypersons on legal-advice sites use everyday words; court decisions use
# legal vocabulary, so a search for the colloquial term misses the bulk of
# on-point cases (measured: "Blitzer" 285 vs "Geschwindigkeitsüberschreitung"
# 1590).
#
# These are applied **at QUERY time only** (the ``german_legal_search``
# search-analyzer, NOT the index analyzer) and are mostly **directional**
# (``a => a, b, c``): querying the colloquial term ALSO matches the
# technical terms, but querying the precise technical term is NOT broadened
# — so professional/precise searches stay unpolluted. (Verified via
# ``_analyze`` + a probe index before rollout.)
#
# Deliberately conservative: only colloquial terms that are effectively
# UNAMBIGUOUS in a legal corpus are mapped. Excluded on purpose:
#   * ``Punkte`` (Flensburg) — far too polysemous (points in any context);
#   * ``Chef`` -> Arbeitgeber — "Chef" is ambiguous (boss/head generally);
#   * generic slang (``Abzocke``, ``Kohle``) — no clean legal referent.
# Extend cautiously; every entry trades a little precision for recall.
CONCEPT_SYNONYMS = [
    # Verkehrsrecht: speed-camera slang -> the measurement / the offence.
    "blitzer, geblitzt => blitzer, geblitzt, geschwindigkeitsmessung, "
    "geschwindigkeitsüberschreitung, geschwindigkeitsverstoß",
    # Verkehrsrecht: "Knöllchen" (ticket) -> the fine instruments.
    "knöllchen => knöllchen, verwarnungsgeld, bußgeldbescheid",
    # Driving licence: colloquial document -> the legal right.
    "führerschein => führerschein, fahrerlaubnis",
    # Mietrecht: Nebenkosten / Betriebskosten are near-synonyms in rental
    # context — bidirectional is safe and high-value.
    "nebenkosten, betriebskosten => nebenkosten, betriebskosten",
    # Sozialrecht: the same basic-income benefit changed names over time —
    # colloquial "Hartz IV", legacy legal "ALG II", current "Arbeitslosengeld
    # II" / "Bürgergeld" (2023). Laypersons overwhelmingly type "Hartz IV"
    # (691 cases) and miss "Arbeitslosengeld II" (7 792). Multi-word →
    # needs synonym_graph. Directional: expand the colloquial/legacy forms
    # to the legal + current terms; a precise "Arbeitslosengeld II" search
    # stays unbroadened. (Grundsicherung deliberately omitted — it is
    # broader, also covering Grundsicherung im Alter.)
    "hartz iv, hartz4, alg ii => hartz iv, hartz4, alg ii, "
    "arbeitslosengeld ii, bürgergeld",
    # Familienrecht: "Sorgerecht" (colloquial) is the "elterliche Sorge"
    # (legal term). (Multi-word RHS → synonym_graph.)
    "sorgerecht => sorgerecht, elterliche sorge",
    # Insolvenzrecht: "Privatinsolvenz" (colloquial) is the
    # "Verbraucherinsolvenz" (legal), aimed at "Restschuldbefreiung".
    "privatinsolvenz => privatinsolvenz, verbraucherinsolvenz, "
    "restschuldbefreiung",
    # NB: excluded "Umgangsrecht => Umgang" — "Umgang" is polysemous
    # (handling/dealing-with in any context), would over-broaden.
]


class BaseConfiguration(Configuration):
    """Base configuration, all deployment configs (dev, prod, test, ...) inherits from this class."""

    DEBUG = False

    # Default primary key field type
    # https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

    DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

    # Make this unique, and don't share it with anybody.
    SECRET_KEY = "something_secret"

    SITE_NAME = values.Value("OLDP")
    SITE_EMAIL = values.Value("hello@openlegaldata.io")
    SITE_URL = values.Value("http://localhost:8000")
    SITE_TITLE = values.Value("Open Legal Data")
    SITE_ICON = values.Value("fa-balance-scale")
    SITE_TWITTER_URL = values.Value("https://twitter.com/openlegaldata")
    SITE_GITHUB_URL = values.Value("https://github.com/openlegaldata")
    SITE_LINKEDIN_URL = values.Value(
        "https://www.linkedin.com/company/open-legal-data/"
    )
    SITE_DISCORD_URL = values.Value("#discord")

    SITE_BLOG_URL = values.Value("//openlegaldata.io/blog")
    SITE_API_DOCS_URL = values.Value("https://openlegaldata.github.io/oldp/")

    SITE_ID = 1

    INTERNAL_IPS = values.TupleValue(("127.0.0.1",))

    ALLOWED_HOSTS = values.ListValue(["127.0.0.1", "localhost"])

    CSRF_TRUSTED_ORIGINS = values.ListValue([])

    # Slugs of LawBooks shown as "top books" on /law/ in the order listed.
    # Empty/unset hides the top block. Read from env var DJANGO_TOP_LAW_BOOKS
    # as a comma-separated string (e.g. "gg,bgb,stgb,hgb,estg").
    TOP_LAW_BOOKS = values.ListValue([])

    # Application definition
    INSTALLED_APPS = [
        # local apps
        "oldp.apps.accounts.apps.AccountsConfig",
        "oldp.apps.laws.apps.LawsConfig",
        "oldp.apps.homepage.apps.HomepageConfig",
        "oldp.apps.cases.apps.CasesConfig",
        "oldp.apps.topics.apps.TopicsConfig",
        "oldp.apps.processing.apps.ProcessingConfig",
        "oldp.apps.search.apps.SearchConfig",
        "oldp.apps.courts.apps.CourtsConfig",
        "oldp.apps.references.apps.ReferencesConfig",
        "oldp.apps.contact.apps.ContactConfig",
        "oldp.apps.annotations.apps.AnnotationsConfig",
        "oldp.apps.sources.apps.SourcesConfig",
        "oldp.apps.lib.apps.LibConfig",
        # third party apps
        # 'pipeline',  # build sass
        "compressor",
        "dal",
        "dal_select2",
        "haystack",
        # 'ckeditor',  # disable due to unfixed security issue
        "drf_yasg",
        "rest_framework",
        "rest_framework.authtoken",
        "django_filters",
        # 'envelope',  # contact form
        # 'tellme',  # feedback
        "widget_tweaks",  # forms
        "crispy_forms",
        "crispy_bootstrap4",
        "mathfilters",  # math filters for templates
        # 'bootstrapform',
        "allauth",
        "allauth.account",
        "allauth.socialaccount",
        # 'allauth.socialaccount.providers.google',
        # 'allauth.socialaccount.providers.github',
        # 'allauth.socialaccount.providers.twitter',
        # MCP + OAuth
        "oauth2_provider",
        "mcp_server",
        "oldp.apps.mcp.apps.MCPConfig",
        # django internal
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.sites",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.humanize",
        "django.contrib.staticfiles",
        "django.contrib.flatpages",
        "django.contrib.sitemaps",
    ]

    CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"

    CRISPY_TEMPLATE_PACK = "bootstrap4"

    # ############## PATHS ###############

    BASE_DIR = Path(os.path.abspath(__file__)).parent.parent

    PACKAGE_DIR = BASE_DIR / "oldp"
    APPS_DIR = PACKAGE_DIR / "apps"
    ASSETS_DIR = PACKAGE_DIR / "assets"
    WORKING_DIR = BASE_DIR / "workingdir"

    # Email settings
    DEFAULT_FROM_EMAIL = values.Value("no-reply@openlegaldata.io")
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = values.Value("localhost")
    EMAIL_PORT = values.IntegerValue(25)
    EMAIL_USE_TLS = values.BooleanValue(False)
    EMAIL_HOST_USER = values.Value("")
    EMAIL_HOST_PASSWORD = values.Value("")

    # Rotating-file log retention. Defaults give ~150 MB total
    # (15 MB × 10 backups), which under heavy bot traffic is only a few
    # hours of history. Raise via env var in production to keep enough
    # history for incident analysis. Applied to LOGGING in
    # ``_apply_dynamic_settings`` below.
    LOG_MAX_BYTES = values.IntegerValue(1024 * 1024 * 15)
    LOG_BACKUP_COUNT = values.IntegerValue(10)

    # AnonymousPublicCacheMiddleware — see oldp/utils/middleware.py.
    # Makes anonymous GETs on public paths CDN-cacheable by stripping
    # Vary: Cookie and Set-Cookie and emitting Cache-Control: public.
    ANON_CACHE_ENABLED = values.BooleanValue(True)
    ANON_CACHE_PATH_PREFIXES = values.ListValue(
        ["/case/", "/law/", "/court/", "/pages/", "/search/"]
    )
    ANON_CACHE_PATHS_EXACT = values.ListValue(["/"])
    ANON_CACHE_S_MAXAGE = values.IntegerValue(600)
    ANON_CACHE_MAX_AGE = values.IntegerValue(60)

    MIDDLEWARE = [
        # Runs last on the response phase (it's first in the list), so it
        # sees the final Vary/Set-Cookie set by Django and can normalize
        # them for CDN-friendly caching of anonymous responses.
        "oldp.utils.middleware.AnonymousPublicCacheMiddleware",
        "django.middleware.gzip.GZipMiddleware",
        "django.middleware.http.ConditionalGetMiddleware",
        # Simplified static file serving.
        # https://warehouse.python.org/project/whitenoise/
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "oldp.apps.lib.apps.DomainLocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "django.contrib.flatpages.middleware.FlatpageFallbackMiddleware",
        # 'pipeline.middleware.MinifyHTMLMiddleware',
        "allauth.account.middleware.AccountMiddleware",
    ]

    ROOT_URLCONF = "oldp.urls"

    TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [PACKAGE_DIR / "assets/templates"],
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.debug",
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                    "oldp.apps.lib.context_processors.global_context_processor",
                ],
            },
        },
    ]

    WSGI_APPLICATION = "oldp.wsgi.application"

    # Messages

    MESSAGE_LEVEL = message_constants.DEBUG
    MESSAGE_TAGS = {
        message_constants.DEBUG: "alert-info",
        message_constants.INFO: "alert-info",
        message_constants.SUCCESS: "alert-success",
        message_constants.WARNING: "alert-warning",
        message_constants.ERROR: "alert-danger",
    }

    # Password validation
    # https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

    AUTH_PASSWORD_VALIDATORS = [
        {
            "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
        },
    ]

    AUTHENTICATION_BACKENDS = (
        # Needed to login by username in Django admin, regardless of `allauth`
        "django.contrib.auth.backends.ModelBackend",
        # `allauth` specific authentication methods, such as login by e-mail
        "allauth.account.auth_backends.AuthenticationBackend",
        # OAuth2 for MCP connector authentication
        "oauth2_provider.backends.OAuth2Backend",
    )

    LOGIN_REDIRECT_URL = "/accounts/email/"
    # ACCOUNT_EMAIL_REQUIRED = True
    ACCOUNT_EMAIL_VERIFICATION = "mandatory"
    ACCOUNT_USERNAME_BLACKLIST = ["admin", "oldp", "openlegaldata"]
    ACCOUNT_USERNAME_MIN_LENGTH = 3

    ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]

    # Custom adapter for graceful email error handling
    ACCOUNT_ADAPTER = "oldp.apps.accounts.adapters.CustomAccountAdapter"

    # Internationalization
    # https://docs.djangoproject.com/en/5.0/topics/i18n/

    # Select language based on domain
    # https://7webpages.com/blog/switch-language-regarding-of-domain-in-django/

    # Set like this: DJANGO_LANGUAGES_DOMAINS="{'de.foo.com':'de','fr.foo.com':'fr'}"
    LANGUAGES_DOMAINS = values.DictValue(
        {
            "localhost:8000": "en",
            "oldp.local:8000": "en",
            "de.oldp.local:8000": "de",
            "127.0.0.1:8000": "de",
        }
    )

    LANGUAGE_CODE = "en"

    LANGUAGES = (
        ("en", _("English")),
        ("de", _("German")),
    )

    LOCALE_PATHS = (PACKAGE_DIR / "locale",)

    TIME_ZONE = "UTC"

    USE_I18N = True

    USE_L10N = True

    USE_TZ = True

    PAGINATE_BY = 50  # Items per page

    PAGINATE_UNTIL = 10  # Max. number of pages

    BULK_EXPORT_URL = values.Value("https://static.openlegaldata.io/dumps/")

    DATABASES = values.DatabaseURLValue("sqlite:///dev.db")

    # Caching

    CACHE_DISABLE = values.BooleanValue(False)
    # Default TTL for cached API/HTML views, in seconds. Long-tail content
    # (case detail, law detail, court lists) changes slowly; 6h is a good
    # tradeoff between freshness and origin-load reduction.
    CACHE_TTL = values.IntegerValue(60 * 60 * 6)
    # Longer TTL for stats endpoints — these aggregate over the full corpus
    # and update only as new cases are ingested. 24h keeps them cheap.
    CACHE_TTL_STATS = values.IntegerValue(60 * 60 * 24)
    CACHE_BACKEND = values.Value("file", environ_name="CACHE_BACKEND")

    # Profiling toggles (enable temporarily on production)
    PROFILING_ENABLED = values.BooleanValue(False, environ_name="PROFILING_ENABLED")
    QUERYCOUNT_ENABLED = values.BooleanValue(False, environ_name="QUERYCOUNT_ENABLED")

    # Honor the 'X-Forwarded-Proto' header for request.is_secure()
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Static files (CSS, JavaScript, Images)
    # https://docs.djangoproject.com/en/1.9/howto/static-files/
    STATIC_ROOT = PACKAGE_DIR / "assets/static-dist"
    STATIC_URL = "/static/"

    STATICFILES_FINDERS = (
        "django.contrib.staticfiles.finders.FileSystemFinder",
        "django.contrib.staticfiles.finders.AppDirectoriesFinder",
        "compressor.finders.CompressorFinder",
    )

    # Extra places for collectstatic to find static files.
    STATICFILES_DIRS = [PACKAGE_DIR / "assets/static"]

    # Set compress compilers
    COMPRESS_ENABLED = True
    COMPRESS_OFFLINE = True

    COMPRESS_PRECOMPILERS = [
        # SASS compiler
        ("text/x-scss", "sass {infile} {outfile}"),
        # ('text/x-scss', 'django_libsass.SassCompiler'),
    ]
    COMPRESS_OUTPUT_DIR = "cache"

    MEDIA_ROOT = BASE_DIR / "media"
    MEDIA_URL = "/media/"

    # Simplified static file serving.
    # https://warehouse.python.org/project/whitenoise/

    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

    # Tellme feedback
    # TELLME_FEEDBACK_EMAIL = values.Value('hello@openlegaldata.io', environ_name='FEEDBACK_EMAIL')

    # CKEditor (wysiwyg)
    # disabled due to unfixed security issue

    # Elasticsearch
    ELASTICSEARCH_URL = values.Value(
        "http://localhost:9200/", environ_name="ELASTICSEARCH_URL"
    )
    ELASTICSEARCH_INDEX = values.Value("oldp", environ_name="ELASTICSEARCH_INDEX")
    # Per-call ES timeout (seconds). Must leave headroom under
    # ``GUNICORN_TIMEOUT`` so Django catches the ``ConnectionTimeout``
    # and runs the ``SearchBackendTimeout`` handler before gunicorn
    # kills the worker. With ``retry_on_timeout=True`` and
    # ``max_retries=1`` the wall-clock cost is at most ``2 *
    # ELASTICSEARCH_TIMEOUT``, so pick well under half of
    # ``GUNICORN_TIMEOUT``.
    #
    # Default 5s keeps the first attempt + retry inside a 9s
    # gunicorn budget while still tolerating cold-cache reads.
    ELASTICSEARCH_TIMEOUT = values.IntegerValue(5, environ_name="ELASTICSEARCH_TIMEOUT")

    HAYSTACK_CONNECTIONS = {
        "default": {
            "ENGINE": "oldp.apps.search.search_backend.SearchEngine",
            "URL": values.Value(
                "http://localhost:9200/", environ_name="ELASTICSEARCH_URL"
            ),
            "INDEX_NAME": values.Value("oldp", environ_name="ELASTICSEARCH_INDEX"),
            # Resolved at setup_dynamic_settings time — see the override
            # in ``setup_dynamic_settings`` below.
            "TIMEOUT": 5,
            "SILENTLY_FAIL": False,
            "KWARGS": {
                "retry_on_timeout": True,
                "max_retries": 1,
            },
        },
    }

    ELASTICSEARCH_INDEX_SETTINGS = {
        "settings": {
            "number_of_replicas": 0,
            "refresh_interval": "60s",
            # German-language analysis for free-text legal fields. Without
            # this, haystack indexes everything with its default "snowball"
            # (English) analyzer, so German morphology is invisible:
            # ``Vertrag`` doesn't match ``Verträge`` and ``Maßnahme``
            # doesn't match ``Massnahme`` (see search-improvements.md §C).
            # Applied to text/title/exact_matches only — see
            # ``SearchBackend.build_schema``. Requires a reindex to take
            # effect (analyzers are fixed at index-creation time).
            "analysis": {
                "filter": {
                    # LIGHT stemmer on purpose. The aggressive snowball
                    # "german" stemmer over-stems and creates false merges
                    # (``Kündigung`` -> "kundig", colliding with
                    # ``kundig`` = knowledgeable), which hurts precision in
                    # legal search. ``light_german`` folds plurals/cases and
                    # normalizes umlauts without collapsing distinct lemmas.
                    "german_light_stem": {
                        "type": "stemmer",
                        "language": "light_german",
                    },
                    # Legal-domain equivalences stemming can't fold
                    # (gendered -in forms, Fugen-s spelling). See
                    # ``LEGAL_SYNONYMS`` above.
                    "legal_synonyms": {
                        "type": "synonym",
                        "synonyms": LEGAL_SYNONYMS,
                    },
                    # Colloquial -> technical expansion, QUERY-TIME ONLY
                    # (used only by ``german_legal_search`` below). Mostly
                    # directional so professional searches stay precise.
                    # ``synonym_graph`` (not plain ``synonym``) so multi-word
                    # terms work — e.g. "Hartz IV" / "ALG II" -> "Arbeitslosen-
                    # geld II". Safe as a search-time filter.
                    "concept_synonyms": {
                        "type": "synonym_graph",
                        "synonyms": CONCEPT_SYNONYMS,
                    },
                },
                "analyzer": {
                    # INDEX analyzer. Order matters: lowercase first, then
                    # expand the (bidirectional) legal_synonyms on surface
                    # forms, then normalize (ß/umlaut) and stem the whole
                    # expanded set so a synonym and its target collapse to
                    # one lemma. No stopword filter: legal exact-phrase
                    # queries must keep function words ("des", "und") so
                    # phrase token positions still line up after analysis.
                    "german_legal": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "legal_synonyms",
                            "german_normalization",
                            "german_light_stem",
                        ],
                    },
                    # SEARCH analyzer = german_legal + the query-time-only
                    # concept_synonyms. Applied as ``search_analyzer`` on the
                    # text fields (see ``SearchBackend.build_schema``) so
                    # colloquial queries expand to technical vocabulary
                    # WITHOUT re-indexing documents and without polluting
                    # precise/technical-term searches (directional synonyms).
                    "german_legal_search": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "legal_synonyms",
                            "concept_synonyms",
                            "german_normalization",
                            "german_light_stem",
                        ],
                    },
                },
            },
        }
    }

    # Search API: max number of highlight snippets returned per result
    SEARCH_MAX_SNIPPETS = 3
    SEARCH_SNIPPET_SIZE = 200

    # Logging
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(asctime)s %(levelname)-8s %(name)-12s %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
            },
            "logfile": {
                "level": "DEBUG",
                "class": "oldp.utils.log_handlers.ModeAwareRotatingFileHandler",
                "filename": BASE_DIR / "logs/oldp.log",
                "maxBytes": 1024 * 1024 * 15,  # 15MB
                "backupCount": 10,
                "formatter": "console",
            },
            # Add Handler for Sentry for `warning` and above
            # 'sentry': {
            #     'level': 'WARNING',
            #     'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
            # },
        },
        "loggers": {
            "": {  # root logger
                "level": "INFO",
                "handlers": ["console", "logfile"],
            },
            "oldp": {
                "level": "DEBUG",
            },
            "refex": {
                "level": "DEBUG",
            },
            "requests": {"level": "ERROR"},
            "elasticsearch": {"level": "ERROR"},
        },
    }

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
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
        ],
        "DEFAULT_PAGINATION_CLASS": "oldp.api.CappedLimitOffsetPagination",
        "DEFAULT_FILTER_BACKENDS": (
            "django_filters.rest_framework.DjangoFilterBackend",
        ),
        "PAGE_SIZE": 50,
        "DEFAULT_RENDERER_CLASSES": (
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
            "rest_framework_xml.renderers.XMLRenderer",
        ),
        # Auth
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "oldp.apps.accounts.authentication.CombinedTokenAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_THROTTLE_CLASSES": (
            "rest_framework.throttling.AnonRateThrottle",
            "oldp.api.throttling.TokenUserRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {
            "anon": "100/day",
            "user": "5000/hour",
        },
        "EXCEPTION_HANDLER": "oldp.api.exceptions.full_details_exception_handler",
    }

    SWAGGER_SETTINGS = {
        "SECURITY_DEFINITIONS": {
            "api_key": {"type": "apiKey", "in": "header", "name": "Authorization"}
        },
    }

    # Processing pipeline
    PROCESSING_STEPS = {
        "Case": [
            "oldp.apps.cases.processing.processing_steps.assign_court",
            "oldp.apps.cases.processing.processing_steps.extract_refs",
            "oldp.apps.cases.processing.processing_steps.generate_related",
            "oldp.apps.cases.processing.processing_steps.set_review_pending",
            "oldp.apps.cases.processing.processing_steps.set_review_accepted",
            "oldp.apps.cases.processing.processing_steps.set_review_rejected",
        ],
        "Law": [
            "oldp.apps.laws.processing.processing_steps.extract_refs",
            "oldp.apps.laws.processing.processing_steps.set_review_pending",
            "oldp.apps.laws.processing.processing_steps.set_review_accepted",
        ],
        "LawBook": [
            "oldp.apps.topics.processing.processing_steps.assign_topics_to_law_book",
            "oldp.apps.laws.processing.processing_steps.set_lawbook_review_pending",
            "oldp.apps.laws.processing.processing_steps.set_lawbook_review_accepted",
        ],
        "Court": [
            "oldp.apps.courts.processing.processing_steps.enrich_from_wikipedia",
            "oldp.apps.courts.processing.processing_steps.set_aliases",
            "oldp.apps.courts.processing.processing_steps.assign_jurisdiction",
            "oldp.apps.courts.processing.processing_steps.set_review_pending",
            "oldp.apps.courts.processing.processing_steps.set_review_accepted",
        ],
        "Reference": [
            "oldp.apps.references.processing.processing_steps.assign_refs",
        ],
    }

    # Courts
    COURT_JURISDICTIONS = {}
    COURT_LEVELS_OF_APPEAL = {}
    COURT_TYPES = CourtTypesDefault()

    # Case creation API validation settings
    # These settings control input validation for the case creation API endpoint
    CASE_CREATION_VALIDATION = {
        "content_min_length": 10,  # Minimum case content length
        "content_max_length": 10000000,  # Maximum case content length (10MB)
        "file_number_min_length": 1,  # Minimum file number length
        "file_number_max_length": 100,  # Maximum file number length
        "title_max_length": 255,  # Maximum title length
        "abstract_max_length": 50000,  # Maximum abstract length
        "court_name_max_length": 255,  # Maximum court name length
    }

    ########################
    # MCP Server
    ########################

    DJANGO_MCP_ENDPOINT = "mcp"
    DJANGO_MCP_GLOBAL_SERVER_CONFIG = {
        "name": "oldp",
        "instructions": (
            "Open Legal Data Platform (OLDP) - German legal data including court "
            "decisions and legislation with cross-references.\n"
            "Start with get_platform_info to understand data coverage.\n"
            "Use search_cases for full-text search, filter_cases for structured queries.\n"
            "Use get_case to retrieve full text (truncated by default, use "
            "full_text=True for complete text).\n"
            "Cross-reference tools (get_case_references, get_citing_cases, "
            "get_cases_for_law) let you navigate the citation graph between cases "
            "and laws.\n"
            "References are automatically extracted and may be incomplete - verify "
            "critical citations against the full text."
        ),
        "stateless": True,
    }
    DJANGO_MCP_GET_SERVER_INSTRUCTIONS_TOOL = True

    # MCP rate limiting (env-configurable)
    MCP_ANTHROPIC_ANON_RATE = values.Value(
        "500/hour", environ_name="MCP_ANTHROPIC_ANON_RATE"
    )
    MCP_USER_RATE = values.Value("1000/hour", environ_name="MCP_USER_RATE")

    ########################
    # OAuth2 (MCP connector auth)
    ########################

    OAUTH2_PROVIDER = {
        "SCOPES": {"read": "Read access to legal data"},
        "DEFAULT_SCOPES": ["read"],
        "PKCE_REQUIRED": True,
        "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
        "REQUEST_APPROVAL_PROMPT": "auto",
        "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
        "REFRESH_TOKEN_EXPIRE_SECONDS": 86400 * 30,
        "ROTATE_REFRESH_TOKEN": True,
    }

    #######################
    # Setup methods
    #######################

    @classmethod
    def setup(cls):
        """Resolve settings values and apply dynamic runtime configuration."""
        super().setup()
        cls._apply_dynamic_settings()

    @classmethod
    def _apply_dynamic_settings(cls):
        """Apply dynamic settings mutations once per configuration class."""
        if getattr(cls, "_DYNAMIC_SETTINGS_APPLIED", False):
            return
        cls._DYNAMIC_SETTINGS_APPLIED = True

        # django-configurations resolves Value descriptors declared on the selected
        # class, but inherited Value fields can still be unresolved here. We rely on
        # several inherited flags/env values below.
        for attr_name in (
            "CACHE_BACKEND",
            "CACHE_DISABLE",
            "ELASTICSEARCH_TIMEOUT",  # consumed by SearchBackend.__init__
            "MCP_ANTHROPIC_ANON_RATE",
            "MCP_USER_RATE",
            "PROFILING_ENABLED",
            "QUERYCOUNT_ENABLED",
        ):
            attr_value = getattr(cls, attr_name, None)
            if isinstance(attr_value, Value):
                setup_value(cls, attr_name, attr_value)

        # ``ELASTICSEARCH_TIMEOUT`` is read by ``SearchBackend.__init__``
        # at construction time — see ``oldp.apps.search.search_backend``.
        # We don't mutate ``HAYSTACK_CONNECTIONS`` here because
        # ``TestConfiguration`` overrides it as a ``@property`` (fresh
        # dict per access), so the mutation would be lost.

        if cls.DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
            # Force strict mode (MySQL only)
            # https://stackoverflow.com/questions/23022858/force-strict-sql-mode-in-django
            if "OPTIONS" not in cls.DATABASES["default"]:
                cls.DATABASES["default"]["OPTIONS"] = {}

            cls.DATABASES["default"]["OPTIONS"]["sql_mode"] = "traditional"
            cls.DATABASES["default"]["OPTIONS"]["charset"] = "utf8mb4"

            cls.DATABASE_MYSQL = True
        else:
            cls.DATABASE_MYSQL = False

        # Dynamic cache configuration based on CACHE_BACKEND environment variable
        if cls.CACHE_BACKEND == "redis":
            cls.CACHES = {
                "default": {
                    "BACKEND": "django_redis.cache.RedisCache",
                    "LOCATION": values.Value(
                        "redis://127.0.0.1:6379/1", environ_name="REDIS_URL"
                    ),
                    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
                }
            }
        else:  # Default to file-based cache
            cls.CACHES = {
                "default": {
                    "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                    "LOCATION": values.Value(
                        "/var/tmp/django_cache", environ_name="FILE_CACHE_LOCATION"
                    ),
                }
            }

        # Disable cache
        if cls.DEBUG and cls.CACHE_DISABLE:
            cls.CACHES["default"]["BACKEND"] = (
                "django.core.cache.backends.dummy.DummyCache"
            )

        # Django Silk profiling
        if cls.PROFILING_ENABLED:
            cls.INSTALLED_APPS = list(cls.INSTALLED_APPS) + ["silk"]
            cls.MIDDLEWARE = list(cls.MIDDLEWARE) + [
                "silk.middleware.SilkyMiddleware",
            ]
            cls.SILKY_INTERCEPT_PERCENT = 100
            cls.SILKY_MAX_RECORDED_REQUESTS = 10_000
            cls.SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 10
            cls.SILKY_PYTHON_PROFILER = True
            cls.SILKY_PYTHON_PROFILER_RESULT_PATH = str(
                cls.WORKING_DIR / "silk-profiles/"
            )
            cls.SILKY_AUTHENTICATION = True
            cls.SILKY_AUTHORISATION = True
            cls.SILKY_META = True

        # Django querycount header
        if cls.QUERYCOUNT_ENABLED:
            cls.MIDDLEWARE = list(cls.MIDDLEWARE) + [
                "querycount.middleware.QueryCountMiddleware",
            ]
            cls.QUERYCOUNT = {
                "THRESHOLDS": {
                    "MEDIUM": 50,
                    "HIGH": 200,
                    "MIN_TIME_TO_LOG": 0,
                    "MIN_QUERY_COUNT_TO_LOG": 0,
                },
                "DISPLAY_DUPLICATES": 5,
            }

        # Overwrite log filename
        log_file = values.Value(default=None, environ_name="LOG_FILE")

        if (
            "handlers" in cls.LOGGING
            and "logfile" in cls.LOGGING["handlers"]
            and log_file
        ):
            cls.LOGGING["handlers"]["logfile"]["filename"] = os.path.join(
                cls.BASE_DIR, "logs", log_file
            )

        # Apply env-configurable rotation parameters to the logfile
        # handler. LOG_MAX_BYTES/LOG_BACKUP_COUNT are resolved by
        # django-configurations at this point.
        if "handlers" in cls.LOGGING and "logfile" in cls.LOGGING["handlers"]:
            cls.LOGGING["handlers"]["logfile"]["maxBytes"] = cls.LOG_MAX_BYTES
            cls.LOGGING["handlers"]["logfile"]["backupCount"] = cls.LOG_BACKUP_COUNT

    @classmethod
    def post_setup(cls):
        """Keep compatibility with django-configurations post_setup hook."""
        cls._apply_dynamic_settings()


class DevConfiguration(BaseConfiguration):
    """Development settings (debugging enabled)"""

    DEBUG = True

    ALLOWED_HOSTS = ["*"]

    COMPRESS_OFFLINE = False

    INSTALLED_APPS = BaseConfiguration.INSTALLED_APPS + [
        "debug_toolbar",
    ]

    MIDDLEWARE = BaseConfiguration.MIDDLEWARE + [
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ]


class TestConfiguration(BaseConfiguration):
    """Use these settings for unit testing"""

    DEBUG = True

    COMPRESS_OFFLINE = False
    COMPRESS_ENABLED = False
    COMPRESS_PRECOMPILERS = []  # Disable SCSS compilation in tests

    DATABASES = values.DatabaseURLValue("sqlite:///test.db")
    ELASTICSEARCH_INDEX = values.Value("oldp_test")

    # Control mocking: True = use mocks (default), False = use real ES
    MOCK_ES_TESTS = values.BooleanValue(True)

    # Enable ES tests by default (they now run with mocks)
    TEST_WITH_ES = values.BooleanValue(True)
    TEST_WITH_WEB = values.BooleanValue(False)
    TEST_WITH_SELENIUM = values.BooleanValue(False)

    @property
    def HAYSTACK_CONNECTIONS(self):
        """Configure Haystack to use mock or real Elasticsearch based on settings."""
        if self.MOCK_ES_TESTS:
            return {
                "default": {
                    "ENGINE": "oldp.apps.search.mock_backend.MockElasticsearchEngine",
                }
            }
        return {
            "default": {
                "ENGINE": "oldp.apps.search.search_backend.SearchEngine",
                "URL": "http://localhost:9200/",
                "INDEX_NAME": "oldp_test",
            }
        }

    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    CACHE_DISABLE = True
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }

    # Override logging to suppress expected logs during tests
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(asctime)s %(levelname)-8s %(name)-12s %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
                "level": "CRITICAL",  # Only show critical errors in console
            },
        },
        "loggers": {
            "": {  # root logger - suppress all but critical
                "level": "CRITICAL",
                "handlers": ["console"],
            },
            "django": {"level": "CRITICAL"},
            "django.request": {"level": "CRITICAL"},
            "oldp": {"level": "CRITICAL"},
            "refex": {"level": "CRITICAL"},
            "haystack": {"level": "CRITICAL"},
            "elasticsearch": {"level": "CRITICAL"},
        },
    }

    @classmethod
    def post_setup(cls):
        """Override post_setup to skip LOGGING modification since it's a property"""
        # Handle DATABASE setup
        if cls.DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
            if "OPTIONS" not in cls.DATABASES["default"]:
                cls.DATABASES["default"]["OPTIONS"] = {}
            cls.DATABASES["default"]["OPTIONS"]["sql_mode"] = "traditional"
            cls.DATABASE_MYSQL = True
        else:
            cls.DATABASE_MYSQL = False

        # CACHES already set in TestConfiguration, no need to modify
        # LOGGING is a property in TestConfiguration, skip modification


class ProdConfiguration(BaseConfiguration):
    """Production settings (override default values with environment vars"""

    SECRET_KEY = values.SecretValue()

    DEBUG = False

    ALLOWED_HOSTS = values.ListValue(["de.openlegaldata.io", "localhost"])

    ADMINS = values.SingleNestedTupleValue()

    # Override logging to set INFO level for production
    @property
    def LOGGING(self):
        """Set log level to INFO for production to reduce verbosity"""
        config = super().LOGGING.copy()
        # Update oldp and refex loggers to INFO level instead of DEBUG
        config["loggers"]["oldp"]["level"] = "INFO"
        config["loggers"]["refex"]["level"] = "INFO"
        return config
