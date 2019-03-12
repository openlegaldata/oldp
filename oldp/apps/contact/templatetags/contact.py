from urllib.parse import quote_plus

from django import template
from django.conf import settings
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def report_content_url(context):
    """
    Get URL to report content form with the current URL attached to it
    """
    request = context['request']

    # We use only the path here, ignoring all GET parameters
    source_url = settings.SITE_URL + request.path

    return reverse('contact:report_content') + '?source=' + quote_plus(source_url)
