import re

from django.utils.encoding import force_str
from rest_framework_xml.renderers import XMLRenderer

# C0 control characters XML 1.0 cannot represent (tab, LF and CR are allowed).
# Same set Django's ``SimplerXMLGenerator.characters`` rejects.
XML_ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class SafeXMLRenderer(XMLRenderer):
    r"""XML renderer that drops characters XML 1.0 cannot represent.

    Court decisions and laws are imported from many sources, and a few
    texts carry stray control characters (e.g. ``\x0b`` vertical tabs from
    word-processor exports). JSON escapes them, but the stock
    ``XMLRenderer`` passes them to Django's ``SimplerXMLGenerator``, which
    raises ``UnserializableContentError`` — the whole response became a
    500. They carry no meaning in legal text, so strip them from every
    text node instead.
    """

    def _to_xml(self, xml, data):
        if data is None or isinstance(data, (list, tuple, dict)):
            # The parent recurses into containers via ``self._to_xml``.
            super()._to_xml(xml, data)
        else:
            xml.characters(XML_ILLEGAL_CHARS.sub("", force_str(data)))
