import hashlib
import json
import logging
import re
import uuid

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law

logger = logging.getLogger(__name__)


class ReferenceMarker(models.Model):
    """
    Abstract class for reference markers, i.e. the actual reference within a text "§§ 12-14 BGB".

    Marker has a position (start, end, line), unique identifier (uuid, randomly generated), text of the marker as in
    the text, list of references (can be law, case, ...). Implementations of abstract class (LawReferenceMarker, ...)
    have the corresponding source object (LawReferenceMarker: referenced_by = a law object).

    """
    text = models.CharField(max_length=250)  # Text of marker
    uuid = models.CharField(max_length=36)
    start = models.IntegerField(default=0)
    end = models.IntegerField(default=0)
    line = models.CharField(blank=True, max_length=200)
    referenced_by = None
    referenced_by_type = None
    references = []

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO Handle ids with signals?

    def get_referenced_by(self):
        raise NotImplementedError()

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

    def set_references(self, ids_list):
        # TODO Save references to db
        # TODO Assign items after complete data is saved in db
        # print('Save ref ids: %s' % ids_list)
        # print('TODO needs to save ref markers first')
        # exit(1)

        if self.__class__.__name__ == 'LawReferenceMarker':
            reference_type = LawReference
        elif self.__class__.__name__ == 'CaseReferenceMarker':
            reference_type = CaseReference
        else:
            raise ValueError('Cannot determine reference_type: %s' % self.__class__.__name__)

        self.references = []

        # Transform to list if is JSON string
        if isinstance(ids_list, str):
            ids_list = json.loads(ids_list)

        for ref_id in ids_list:
            ref_id = json.dumps(ref_id)
            self.references.append(reference_type(to=ref_id, marker=self))

        self.ids = ids_list

    def save_references(self):
        if self.references:
            for ref in self.references:
                ref.save()
                logger.debug('Saved: %s' % ref)
                # exit(1)
        else:
            logger.debug('No references to save')

    def get_references(self):
        # TODO Get references from db
        if isinstance(self.ids, str):
            self.ids = json.loads(self.ids)

        return self.ids

    def from_ref(self, ref, by):
        self.ids = ref.ids
        self.line = ref.line
        self.start = ref.start
        self.end = ref.end
        self.text = ref.text
        self.uuid = ref.uuid
        self.referenced_by = by

        # self.set_references(self.ids)

        return self

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'RefMarker(ids=%s, line=%s, pos=%i-%i, by=%s)' % ('self.ids', self.line, self.start, self.end, self.referenced_by)

    @staticmethod
    def remove_markers(value):
        return re.sub(r'\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]', r'\2', value)

    @staticmethod
    def make_markers_clickable(value):
        """
        TODO Replace ref marker number with db id
        """
        return re.sub(r'\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]', r'<a href="#refs" onclick="clickRefMarker(this);" data-ref-uuid="\1" class="ref">\2</a>', value)


class LawReferenceMarker(ReferenceMarker):
    """

    A reference marker in a law content object.

    """
    referenced_by_type = Law
    referenced_by = models.ForeignKey(Law, on_delete=models.CASCADE)

    def get_referenced_by(self) -> Law:
        return self.referenced_by


@receiver(pre_save, sender=LawReferenceMarker)
def json_dumps_reference(sender, instance, *args, **kwargs):
    if isinstance(instance.ids, list):
        # Save ids as JSON
        instance.ids = json.dumps(instance.ids)


class CaseReferenceMarker(ReferenceMarker):
    """

    A reference marker in a case content object.

    """
    referenced_by_type = Case
    referenced_by = models.ForeignKey(Case, on_delete=models.CASCADE)

    def get_referenced_by(self) -> Case:
        return self.referenced_by


@receiver(pre_save, sender=CaseReferenceMarker)
def json_dumps_reference(sender, instance, *args, **kwargs):
    if isinstance(instance.ids, list):
        # Save ids as JSON
        instance.ids = json.dumps(instance.ids)


class Reference(models.Model):
    """

    A reference connecting two content objects (1:1 relation). The object that is referenced is either "law", "case"
    or ... (reference target). The referencing object (the object which text contains the reference) can be derived
    via marker.

    Abstract class: Depending on the referencing object (its marker) the corresponding implementation is used.

    If the referenced object is not defined, the reference is "not assigned" (is_assigned method)

    """
    law = models.ForeignKey(Law, null=True, on_delete=models.SET_NULL)
    case = models.ForeignKey(Case, null=True, on_delete=models.SET_NULL)
    to = models.CharField(max_length=250)  # to as string, if case or law cannot be assigned (ref id)
    to_hash = models.CharField(max_length=100, null=True)
    marker = None
    count = None

    class Meta:
        abstract = True

    def get_url(self):
        """
        Returns Url to law or case item (if exist) otherwise return search Url.

        :return:
        """
        if self.law is not None:
            return self.law.get_url()
        elif self.case is not None:
            return self.case.get_url()
        else:
            return '/search/?q=%s' % self.marker.text

    def get_target(self):
        if self.law is not None:
            return self.law
        elif self.case is not None:
            return self.case
        else:
            return None

    def get_title(self):
        if self.law is not None:
            return self.law.get_title()
        elif self.case is not None:
            return self.case.get_title()
        else:
            to = json.loads(self.to)
            to['sect'] = str(to['sect'])

            if to['type'] == 'law' and 'book' in to and 'sect' in to:
                print(to)
                if to['book'] == 'gg':
                    sect_prefix = 'Art.'
                elif 'anlage' in to['sect']:
                    sect_prefix = ''
                else:
                    sect_prefix = '§'
                to['sect'] = to['sect'].replace('anlage-', 'Anlage ')
                return sect_prefix + ' ' + to['sect'] + ' ' + to['book'].upper()
            else:
                return self.marker.text

    def is_assigned(self):
        return self.law is not None or self.case is not None

    def set_to_hash(self):
        m = hashlib.md5()
        m.update(self.to.encode('utf-8'))

        self.to_hash = m.hexdigest()

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        if self.count:
            return 'Reference(count=%i, to=%s, hash=%s)' % (self.count, self.to, self.to_hash)
        else:
        #     return self.__dict__
            return 'Reference(%s, target=%s, marker=%s)' % (self.to, self.get_target(), self.marker)


class LawReference(Reference):
    """

    A reference from a law to any content object (law, case, ...)

    """
    marker = models.ForeignKey(LawReferenceMarker, on_delete=models.CASCADE)


@receiver(pre_save, sender=LawReference)
def pre_save_law_reference(sender, instance, *args, **kwargs):
    instance.set_to_hash()


class CaseReference(Reference):
    """

    A reference from a case to any content object (law, case, ...)

    """
    marker = models.ForeignKey(CaseReferenceMarker, on_delete=models.CASCADE)


@receiver(pre_save, sender=CaseReference)
def pre_save_case_reference(sender, instance, *args, **kwargs):
    instance.set_to_hash()


# @receiver(pre_save, sender=Reference)
# def json_dumps_reference(sender, instance, *args, **kwargs):
#     if not isinstance(instance.to, str):
#         instance.to = json.dumps(instance.to)

# @receiver(post_init, sender=LawReference)
# def json_loads_reference(sender, instance, *args, **kwargs):
#     print(instance.ids)
#     exit(0)
# if instance.ids is not None and isinstance(instance.ids, str):
#     instance.ids = json.loads(instance.ids)

