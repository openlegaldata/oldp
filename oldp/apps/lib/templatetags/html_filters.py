from django import template
from django.utils.safestring import mark_safe

from oldp.apps.lib.html_sanitizer import sanitize_html as _sanitize_html

register = template.Library()


@register.filter(name="sanitize_html", is_safe=True)
def sanitize_html(value):
    """Sanitize untrusted HTML and mark the result safe for rendering.

    Drop-in replacement for wrapping ingested case/law content in
    ``{% autoescape off %}``: it strips any stored ``<script>``/``onerror``/
    ``onclick``/``javascript:`` payload before rendering while preserving
    legitimate markup and the reference/annotation markers.

    Usage: ``{{ content|sanitize_html }}``
    """
    return mark_safe(_sanitize_html(value or ""))
