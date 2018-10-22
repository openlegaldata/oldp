import logging
import uuid
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)


class RefType(Enum):
    CASE = 'case'
    LAW = 'law'


class BaseRef(object):
    ref_type = None  # type: RefType

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        return 'Ref<%s>' % self.__dict__


class CaseRefMixin(BaseRef):
    file_number = ''
    ecli = ''
    court = ''
    date = ''


class LawRefMixin(BaseRef):
    book = ''  # type: str
    section = ''  # type: str
    sentence = '' # type: str


class Ref(LawRefMixin, CaseRefMixin, BaseRef):
    """
    A reference can point to all available types (RefType). Currently either law or case supported.

    """
    pass


class RefMarker(object):
    """
    Abstract class for reference markers, i.e. the actual reference within a text "§§ 12-14 BGB".

    Marker has a position (start, end, line), unique identifier (uuid, randomly generated), text of the marker as in
    the text, list of references (can be law, case, ...). Implementations of abstract class (LawReferenceMarker, ...)
    have the corresponding source object (LawReferenceMarker: referenced_by = a law object).

    """
    text = ''  # Text of marker
    uuid = ''
    start = 0
    end = 0
    line = ''
    references = []  # type: List<Ref>

    # Set by django
    referenced_by = None
    referenced_by_type = None

    def __init__(self, text: str, start: int, end: int, line=''):
        self.text = text
        self.start = start
        self.end = end
        self.line = line

    def replace_content(self, content, marker_offset, key):
        marker_close = '[/ref]'

        start = self.start + marker_offset
        end = self.end + marker_offset

        # marker_open = '[ref=%i]' % key
        # Instead of key use uuid
        marker_open = '[ref=%s]' % self.uuid

        marker_offset += len(marker_open) + len(marker_close)

        # double replacements
        content = content[:start] \
                  + marker_open \
                  + content[start:end] \
                  + marker_close \
                  + content[end:]

        return content, marker_offset

    def set_uuid(self):
        self.uuid = uuid.uuid4()

    def set_references(self, refs: List[Ref]):
        self.references = refs

    def get_references(self) -> List[Ref]:
        return self.references

    def __repr__(self):
        return 'RefMarker<%s>' % self.__dict__
