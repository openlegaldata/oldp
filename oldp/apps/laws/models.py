import datetime
import html
import json
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

from oldp.apps.search.models import RelatedContent, SearchableContent
from oldp.apps.topics.models import TopicContent

logger = logging.getLogger(__name__)


def validate_revision_date(value):
    """Validate that revision date is reasonable (not in future, not too old)."""
    if value > timezone.now().date():
        raise ValidationError(_("Revision date cannot be in the future."))
    if value < datetime.date(1800, 1, 1):
        raise ValidationError(
            _("Revision date cannot be before 1800 (unreasonably old for German laws).")
        )


class LawBook(TopicContent):
    """Law book"""

    title = models.CharField(
        max_length=250, default="Untitled book", help_text="Full title of the book"
    )
    code = models.CharField(max_length=100, help_text="Book code (usually short title)")
    slug = models.SlugField(
        max_length=200,
        help_text="Slugified book code",
        db_index=True,
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text="Indicates importance of this law book (used to order books in front end)",
    )
    revision_date = models.DateField(
        default=datetime.date(1990, 1, 1),
        help_text="Date of revision",
        validators=[validate_revision_date],
    )
    latest = models.BooleanField(
        default=True,
        help_text="Is true if this is the latest revision of this book",
        db_index=True,
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text="Entry is created at this date time",
        db_index=True,
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text="Date time of last change",
        db_index=True,
    )
    created_by_token = models.ForeignKey(
        "accounts.APIToken",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_lawbooks",
        help_text="API token used to create this law book via the API",
    )
    review_status = models.CharField(
        max_length=10,
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
        default="accepted",
        db_index=True,
        help_text="Review status for API-submitted law books",
    )

    # icon = models.CharField(max_length=10, default='§')

    # JSON fields
    changelog = models.TextField(blank=True, default="[]")
    footnotes = models.TextField(blank=True, default="[]")
    sections = models.TextField(blank=True, default="{}")

    # fussnoten = models.TextField(blank=True)
    # es_fields_exclude = ['revision_date']  # LawBook is not searchable

    class Meta:
        unique_together = (("slug", "revision_date"),)
        indexes = [
            models.Index(
                fields=["code", "latest"], name="laws_lawbook_code_latest_idx"
            ),
        ]

    def clean(self):
        """Validate model data before saving."""
        super().clean()
        # Ensure only one book per code can have latest=True
        if self.latest:
            existing = (
                LawBook.objects.filter(code=self.code, latest=True)
                .exclude(pk=self.pk)
                .exists()
            )
            if existing:
                raise ValidationError(
                    {
                        "latest": f"A latest revision already exists for lawbook code '{self.code}'. "
                        "Only one revision can be marked as latest."
                    }
                )

    def get_section(self):
        pass

    def add_section(self, title: str, from_order: int):
        # print(self.sections)
        # print(type(self.sections))
        #
        # print(type(self.get_sections()))
        # exit(0)
        # print(title + '__')
        # print(from_order)
        sects = self.get_sections()
        sects[int(from_order)] = title
        # print(sects)

        self.sections = json.dumps(sects)

    def get_sections(self) -> dict:
        """Get sections as dict without mutating database state."""
        if isinstance(self.sections, str):
            return json.loads(self.sections)
        return self.sections

    def get_title(self):
        return self.title

    def get_short_title(self, length=30):
        if len(self.title) < length:
            return self.title
        else:
            return self.title[:length] + " ..."

    def get_code(self):
        return self.code

    def get_absolute_url(self):
        return reverse("laws:book", args=(self.slug,))

    def get_changelog(self):
        """Get changelog as list without mutating database state."""
        if isinstance(self.changelog, str):
            return json.loads(self.changelog)
        return self.changelog

    def get_changelog_text(self):
        """types: Stand, Hinweis, Sonst

        Format: [{"type":"Stand", "text": "..."}]

        :return:
        """
        ## replace "textlich nachgewiesen, dokumentarisch noch nicht abschließend bearbeitet"
        text = None
        for log in self.get_changelog():
            if log["type"] == "Stand":
                if text is None:
                    text = log["text"]
                else:
                    text += ", " + log["text"]
        return text

    def get_revision_dates(self, limit=0):
        """Get a list of available revision dates for this book (in descending order).

        :param limit: Limit the length of returned list
        :return:
        """
        dates = (
            LawBook.objects.filter(code=self.code)
            .order_by("-revision_date")
            .values_list("revision_date", flat=True)
        )

        if limit > 0:
            dates = dates[:limit]

        return dates

    def __str__(self):
        return "%s (%s)" % (self.title, self.revision_date)


class Law(SearchableContent, models.Model):
    """Law model contains actual law text and belongs to a law book"""

    book = models.ForeignKey(
        LawBook,
        on_delete=models.CASCADE,
        db_index=True,
        help_text="The book this law belongs to",
    )
    created_date = models.DateTimeField(
        auto_now_add=True, help_text="Date of creation of this database entry"
    )
    updated_date = models.DateTimeField(
        auto_now=True, help_text="Last change of database entry"
    )
    content = models.TextField(
        blank=True, help_text="Law content with HTML tags and reference markers"
    )
    title = models.CharField(
        max_length=200, default="", help_text="Verbose title of law"
    )
    slug = models.SlugField(
        max_length=200,
        help_text="Slug based on section",
        db_index=True,
    )
    section = models.CharField(
        blank=True,
        help_text='Section identifier (with § or Art., formerly "enbez")',
        max_length=200,
    )
    amtabk = models.CharField(blank=True, null=True, max_length=200)
    kurzue = models.CharField(blank=True, null=True, max_length=200)
    doknr = models.CharField(
        blank=True,
        null=True,
        max_length=200,
        help_text="Document number as in XML source",
    )
    footnotes = models.TextField(
        blank=True, null=True, help_text="Footnotes as JSON array"
    )
    order = models.PositiveSmallIntegerField(
        default=0, help_text="Order within law book"
    )
    previous = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        related_name="previous_law",
        help_text="Points to previous law based on order value",
        editable=False,
    )
    created_by_token = models.ForeignKey(
        "accounts.APIToken",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_laws",
        help_text="API token used to create this law via the API",
    )
    review_status = models.CharField(
        max_length=10,
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
        default="accepted",
        db_index=True,
        help_text="Review status for API-submitted laws",
    )

    # Internal fields (non db)
    reference_markers = None
    references = None

    # The following fields are excluded from the SELECT-query when querying the database
    defer_fields_list_view = [
        "content",
        "footnotes",
        "book__changelog",
        "book__footnotes",
        "book__sections",
    ]

    class Meta:
        unique_together = (("book", "slug"),)
        indexes = [
            models.Index(fields=["previous"], name="laws_law_previous_idx"),
            models.Index(fields=["book", "order"], name="laws_law_book_order_idx"),
            models.Index(fields=["section"], name="laws_law_section_idx"),
        ]

    def __str__(self):
        return "Law(%s §%s, title=%s)" % (self.book.code, self.slug, self.title)

    def get_html_content(self):
        content = self.content

        from oldp.apps.references.models import LawReferenceMarker

        content = LawReferenceMarker.make_markers_clickable(content)

        return content

    def get_text(self):
        # Convert law content as plain text for ES
        text = strip_tags(html.unescape(self.content))

        from oldp.apps.references.models import LawReferenceMarker

        return LawReferenceMarker.remove_markers(text)

    def is_disabled(self):
        return self.title == "(weggefallen)" and (
            self.content == ""
            or self.content.strip() == "<P/>"
            or self.content.strip() == "<P>-</P>"
        )

    def get_next(self):
        """Get the next law in sequence, or None if this is the last law."""
        try:
            return Law.objects.get(previous=self.id)
        except Law.DoesNotExist:
            return None
        except Law.MultipleObjectsReturned:
            # Data corruption: multiple laws pointing to same previous
            logger.error(f"Multiple laws found with previous={self.id} (Law {self.pk})")
            return Law.objects.filter(previous=self.id).first()

    # def get_previous_url(self):
    #     pass

    def has_footnotes(self):
        return self.footnotes is not None and self.footnotes != ""

    def has_next(self):
        """Check if there is a next law in the sequence."""
        return Law.objects.filter(previous=self.id).exists()

    def get_previous(self):
        return self.previous

    def has_previous(self):
        # pass
        return self.previous is not None

    def get_type(self):
        return self.__class__.__name__

    def get_id(self):
        return self.id

    def get_title(self):
        return "%s %s %s" % (self.book.code, self.section, self.title)

    def get_short_title(self, length=40):
        if len(self.get_title()) < length:
            return self.get_title()
        else:
            return self.get_title()[:length] + " ..."

    def get_book_title(self):
        raise ValueError("Call book directly")

    def get_section(self):  # TODO refactor to chapter
        return self.book.get_sections().get(str(self.order))

    def get_related(self, n=5):
        """Related items that are pre-computed with "generate_related_cases" command.

        :param n: number of items
        :return:
        """
        items = []
        for item in RelatedLaw.objects.filter(seed_content=self).order_by("-score")[:n]:
            items.append(item.related_content)
        return items

    def get_absolute_url(self):
        return reverse(
            "laws:law",
            args=(
                self.book.slug,
                self.slug,
            ),
        )

    def get_latest_revision_url(self):
        """Get URL to this law in the latest revision of the lawbook.

        If the law doesn't exist in the latest revision, returns the book URL.
        """
        try:
            latest_book = LawBook.objects.get(code=self.book.code, latest=True)
            # Check if this law exists in the latest revision
            latest_law = Law.objects.filter(book=latest_book, slug=self.slug).first()
            if latest_law:
                return latest_law.get_absolute_url()
            else:
                # Law doesn't exist in latest revision, link to book instead
                return latest_book.get_absolute_url()
        except LawBook.DoesNotExist:
            # No latest revision found, return current URL
            logger.warning(f"No latest revision found for book code {self.book.code}")
            return self.get_absolute_url()

    def get_api_url(self):
        return "/api/laws/{}/".format(self.pk)

    def get_admin_url(self):
        return reverse("admin:laws_law_change", args=(self.pk,))

    def get_es_url(self):
        return (
            settings.ELASTICSEARCH_URL
            + settings.ELASTICSEARCH_INDEX
            + "/modelresult/laws.law.%s" % self.pk
        )

    def get_referencing_cases_url(self):
        return reverse("cases:index") + "?has_reference_to_law={}".format(self.pk)

    def get_references(self):
        if self.references is None:
            from oldp.apps.references.models import Reference

            self.references = Reference.objects.filter(
                lawreferencemarker__referenced_by=self
            )

        return self.references

    def get_reference_markers(self):
        if self.reference_markers is None:
            from oldp.apps.references.models import LawReferenceMarker

            self.reference_markers = LawReferenceMarker.objects.filter(
                referenced_by=self.id
            )
        return self.reference_markers

    def get_referencing_cases(self, case_queryset):
        """Returns all cases that cite this law

        :param case_queryset: Default queryset for cases (depending on request)
        :return: filtered queryset
        """
        return case_queryset.filter(
            casereferencemarker__referencefromcase__reference__law=self
        ).distinct()


@receiver(pre_save, sender=Law)
def pre_save_law(sender, instance: Law, *args, **kwargs):
    pass


@receiver(post_save, sender=LawBook)
@receiver(post_delete, sender=LawBook)
def invalidate_lawbook_cache(sender, instance, **kwargs):
    """Invalidate cache when a lawbook is updated or deleted."""
    from django.core.cache import cache

    # Clear all cache entries for this lawbook slug
    # The cache_per_user decorator uses view_cache_{path}_{user} format
    # Note: delete_pattern is only available in Redis backend, not LocMemCache
    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern(f"view_cache_*/laws/{instance.slug}/*")
        logger.debug(f"Invalidated cache for lawbook: {instance.slug}")
    # Silently skip cache invalidation when using LocMemCache (test environment)


@receiver(post_save, sender=Law)
@receiver(post_delete, sender=Law)
def invalidate_law_cache(sender, instance, **kwargs):
    """Invalidate cache when a law is updated or deleted."""
    from django.core.cache import cache

    # Clear cache for this specific law
    # Note: delete_pattern is only available in Redis backend, not LocMemCache
    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern(f"view_cache_*/laws/{instance.book.slug}/{instance.slug}*")
        logger.debug(f"Invalidated cache for law: {instance.book.slug}/{instance.slug}")
    # Silently skip cache invalidation when using LocMemCache (test environment)


class RelatedLaw(RelatedContent):
    seed_content = models.ForeignKey(
        Law, related_name="seed_id", on_delete=models.CASCADE
    )
    related_content = models.ForeignKey(
        Law, related_name="related_id", on_delete=models.CASCADE
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["seed_content", "-score"], name="laws_rellaw_seed_score_idx"
            ),
        ]
