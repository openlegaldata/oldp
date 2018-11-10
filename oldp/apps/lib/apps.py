from django.apps import AppConfig
from django.conf import settings
from django.utils import translation


class LibConfig(AppConfig):
    name = 'oldp.apps.lib'

    def ready(self):
        from oldp.apps.lib.templatetags import qstring

        if qstring:
            pass


DEBUG_CONTENT = None


class DomainLocaleMiddleware(object):
    """
    Change language based on domain.

    Taken from: https://7webpages.com/blog/switch-language-regarding-of-domain-in-django/

    """
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        if 'HTTP_ACCEPT_LANGUAGE' in request.META:
            # Totally ignore the browser settings...
            del request.META['HTTP_ACCEPT_LANGUAGE']

        if 'HTTP_HOST' in request.META:
            current_domain = request.META['HTTP_HOST']
            lang_code = settings.LANGUAGES_DOMAINS.get(current_domain)

            if lang_code:
                translation.activate(lang_code)
                request.LANGUAGE_CODE = lang_code

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response


class Counter:
    """
    Helper class for counter in templates

    {{ counter.increment }}
    {{ counter.count }}

    """
    count = 0

    def __init__(self, count=0):
        self.count = count

    def increment(self):
        self.count += 1
        return ''

    def decrement(self):
        self.count -= 1
        return ''


def unset_debug_content():
    global DEBUG_CONTENT

    DEBUG_CONTENT = None


def set_debug_content(public_message, dev_message):
    global DEBUG_CONTENT

    DEBUG_CONTENT = {
        'public_message': public_message,
        'dev_message': dev_message
    }
