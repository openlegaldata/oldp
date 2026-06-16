import hashlib
import logging
import re

from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.urls import reverse

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law
from oldp.apps.lib.markers import BaseMarker
from oldp.apps.search.templatetags.search import search_url

logger = logging.getLogger(__name__)


class Reference(models.Model):
    """A reference connecting two content objects (1:1 relation). The object that is referenced is either "law", "case"
    or ... (reference target). The referencing object (the object which text contains the reference) can be derived
    via marker.

    Depending on the referencing object (its marker) the corresponding implementation is used.

    If the referenced object is not defined, the reference is "not assigned" (is_assigned method)

    """

    law = models.ForeignKey(Law, null=True, blank=True, on_delete=models.SET_NULL)
    case = models.ForeignKey(Case, null=True, blank=True, on_delete=models.SET_NULL)
    # Stable identifiers for the cited law section, decoupled from the
    # specific ``Law`` row's book revision. ``Reference.law`` pins to one
    # row that may belong to a non-latest revision (and so age out as new
    # revisions land); the slug pair ``(law_book_slug, law_section_slug)``
    # identifies the section abstractly. Reverse-citation queries should
    # filter on the slugs so they survive book-revision turnover and
    # avoid the JOIN through ``Law``→``LawBook``.
    law_book_slug = models.CharField(max_length=200, blank=True, db_index=True)
    law_section_slug = models.CharField(max_length=200, blank=True, db_index=True)
    # 1000 (was 250): mirrors ``marker.text`` (set to it in save_citations), so
    # the same long multi-section citation enumerations that overflowed the
    # marker column also overflow this one. Widened in lock-step with
    # ``ReferenceMarker.text`` (#244 only fixed the marker side). utf8mb4
    # varchar(250) already uses a 2-byte length prefix, so → 1000 is INSTANT.
    # TODO: this column duplicates marker.text — consolidate (see follow-up).
    to = models.CharField(
        max_length=1000
    )  # to as string, if case or law cannot be assigned (ref id)
    to_hash = models.CharField(max_length=100, null=True)
    count = None

    class Meta:
        indexes = [
            models.Index(fields=["to_hash"], name="refs_ref_to_hash_idx"),
            models.Index(fields=["law"], name="refs_ref_law_idx"),
            models.Index(
                fields=["law_book_slug", "law_section_slug"],
                name="refs_ref_law_slugs_idx",
            ),
        ]

    def get_marker(self):
        """Reverse m2m-field look up"""
        marker = self.casereferencemarker_set.first()

        if marker is None:
            marker = self.lawreferencemarker_set.first()

        return marker

    def get_admin_url(self):
        return reverse("admin:references_reference_change", args=(self.pk,))

    def get_absolute_url(self):
        """Returns Url to law or case item (if exist) otherwise return search Url.

        :return:
        """
        if self.law is not None:
            return self.law.get_absolute_url()
        elif self.case is not None:
            return self.case.get_absolute_url()
        else:
            return search_url(self.get_marker().text) + "&from=ref"

    def get_target(self):
        if self.has_law_target():
            return self.law
        elif self.has_case_target():
            return self.case
        else:
            return None

    def has_law_target(self):
        return self.law is not None

    def has_case_target(self):
        return self.case is not None

    def get_title(self):
        # TODO handle unassigned refs
        if self.has_law_target():
            return self.law.get_title()
        elif self.has_case_target():
            return self.case.get_title()
        else:
            return self.to  # TODO
            # to = json.loads(self.to)
            # to['sect'] = str(to['sect'])
            #
            # if to['type'] == 'law' and 'book' in to and 'sect' in to:
            #     print(to)
            #     if to['book'] == 'gg':
            #         sect_prefix = 'Art.'
            #     elif 'anlage' in to['sect']:
            #         sect_prefix = ''
            #     else:
            #         sect_prefix = '§'
            #     to['sect'] = to['sect'].replace('anlage-', 'Anlage ')
            #     return sect_prefix + ' ' + to['sect'] + ' ' + to['book'].upper()
            # else:
            #     return self.get_marker().text

    def is_assigned(self):
        return self.has_law_target() or self.has_case_target()

    def save(self, *args, **kwargs):
        """Keep ``law_book_slug`` / ``law_section_slug`` in sync with ``law``.

        The slug pair is the stable identifier used by reverse-citation
        queries; if a caller sets ``ref.law = some_law`` directly we
        copy the law's book + section slugs across so the invariant
        ``(law set ⇒ slugs populated)`` holds. ``assign_law_ref`` does
        this explicitly too; this hook covers tests + ad-hoc admin
        edits that bypass the extraction pipeline.
        """
        if self.law_id:
            if not self.law_book_slug or not self.law_section_slug:
                # Pull from the related Law if we don't already have a
                # cached one. This is rare on the hot path (extraction
                # sets both fields explicitly) so the extra fetch is
                # acceptable cost for invariant safety.
                law = self.law if "law" in self.__dict__ else None
                if law is None:
                    from oldp.apps.laws.models import Law as _Law

                    law = (
                        _Law.objects.select_related("book")
                        .filter(pk=self.law_id)
                        .first()
                    )
                if law is not None:
                    self.law_book_slug = law.book.slug or ""
                    self.law_section_slug = law.slug or ""
        super().save(*args, **kwargs)

    def set_to_hash(self):
        """Generate a unique hash for this reference (used for grouping)"""
        m = hashlib.md5()

        if self.has_law_target():
            hash_this = "law/%i" % self.law_id
        elif self.has_case_target():
            hash_this = "case/%i" % self.case_id
        else:
            hash_this = "unassigend/" + self.to

        m.update(hash_this.encode("utf-8"))

        self.to_hash = m.hexdigest()

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        if self.count:
            return "<Reference(count=%i, to=%s, hash=%s)>" % (
                self.count,
                self.to,
                self.to_hash,
            )
        else:
            #     return self.__dict__
            return "<Reference(%s, target=%s)>" % (self.to, self.get_target())


class ReferenceMarker(models.Model, BaseMarker):
    """Abstract class for reference markers, i.e. the actual reference within a text "§§ 12-14 BGB".

    Marker has a position (start, end, line), text of the marker as in
    the text, list of references (can be law, case, ...). Implementations of abstract class (LawReferenceMarker, ...)
    have the corresponding source object (LawReferenceMarker: referenced_by = a law object).

    """

    # 1000 (was 250): genuine multi-section citation enumerations — e.g.
    # "§ 3 Abs. 2 Satz 1, 11 Abs. 3, ... 121 Satz 2 BSHG" listing ~30 sections —
    # can exceed 250 chars and overflowed the column on re-extraction. utf8mb4
    # varchar(250) already uses a 2-byte length prefix, so widening to 1000 is an
    # INSTANT (metadata-only) ALTER, no table rebuild. See save_citations for the
    # belt-and-suspenders length guard.
    text = models.CharField(
        max_length=1000, help_text="Text that represents the marker (e.g. § 123 ABC)"
    )
    # uuid = models.CharField(max_length=36)  # Deprecated
    start = models.IntegerField(default=0, help_text="Position of marker")
    end = models.IntegerField(
        default=0,
        help_text="Position of marker",
    )
    line_number = models.IntegerField(
        default=0,
        help_text="Number of line, i.e. paragraph, in which marker occurs (0=not set)",
    )
    referenced_by = None
    referenced_by_type = None
    references = None

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO Handle ids with signals?

    def get_referenced_by(self):
        raise NotImplementedError()

    def get_start_position(self):
        return self.start

    def get_end_position(self):
        return self.end

    def get_expected_text(self):
        """Plain-text projection persisted at extraction time.

        :func:`oldp.apps.lib.markers.insert_markers` compares this
        against ``content[start:end]`` and skips the marker on
        mismatch — typically when ``case.content`` was modified after
        the markers were extracted.
        """
        return self.text

    def get_marker_open_format(self):
        return '<a href="#refs" onclick="clickRefMarker(this);" data-marker-id="{id}" class="ref">'

    def get_marker_close_format(self):
        return "</a>"

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "RefMarker(id=%s, line=%s, pos=%i-%i, by=%s)" % (
            self.pk,
            self.line_number,
            self.start,
            self.end,
            self.referenced_by_id,
        )

    @staticmethod
    def remove_markers(value):
        return re.sub(r"\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]", r"\2", value)

    @staticmethod
    def make_markers_clickable(value):
        """TODO Replace ref marker number with db id"""
        return re.sub(
            r"\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]",
            r'<a href="#refs" onclick="clickRefMarker(this);" data-marker-id="\1" class="ref">\2</a>',
            value,
        )


class LawReferenceMarker(ReferenceMarker):
    """A reference marker in a law content object."""

    referenced_by_type = Law
    referenced_by = models.ForeignKey(Law, on_delete=models.CASCADE)
    references = models.ManyToManyField(Reference, through="ReferenceFromLaw")

    def get_referenced_by(self) -> Law:
        return self.referenced_by


class CaseReferenceMarker(ReferenceMarker):
    """A reference marker in a case content object."""

    referenced_by_type = Case
    referenced_by = models.ForeignKey(Case, on_delete=models.CASCADE)
    references = models.ManyToManyField(Reference, through="ReferenceFromCase")

    def get_referenced_by(self) -> Case:
        return self.referenced_by


@receiver(pre_delete, sender=LawReferenceMarker)
@receiver(pre_delete, sender=CaseReferenceMarker)
def pre_delete_reference_marker(sender, instance: ReferenceMarker, *args, **kwargs):
    # Delete all corresponding references
    Reference.objects.filter(pk__in=instance.references.all()).delete()


class ReferenceFromContent(models.Model):
    """Helper class for using `select_related` on ManyToManyField

    Table exist already from ManyToManyField, run migration with:

    ./manage.py migrate --fake references 0007_fake_helper_tables_for_m2m

    """

    reference = models.ForeignKey(Reference, on_delete=models.CASCADE)
    marker = None

    class Meta:
        abstract = True


class ReferenceFromCase(ReferenceFromContent):
    marker = models.ForeignKey(
        CaseReferenceMarker,
        on_delete=models.CASCADE,
        db_column="casereferencemarker_id",
    )

    class Meta:
        db_table = "references_casereferencemarker_references"


class ReferenceFromLaw(ReferenceFromContent):
    marker = models.ForeignKey(
        LawReferenceMarker, on_delete=models.CASCADE, db_column="lawreferencemarker_id"
    )

    class Meta:
        db_table = "references_lawreferencemarker_references"
