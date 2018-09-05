import datetime
import html
import json
import logging

from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.html import strip_tags

from oldp.apps.search.models import SearchableContent, RelatedContent

logger = logging.getLogger(__name__)


class LawBook(models.Model):
    """Law book"""
    title = models.CharField(
        max_length=250,
        default='Untitled book',
        help_text='Full title of the book'
    )
    code = models.CharField(
        max_length=100,
        help_text='Book code (usually short title)'
    )
    slug = models.SlugField(
        max_length=200,
        help_text='Slugified book code'
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text='Indicates importance of this law book (used to order books in front end)'
    )
    revision_date = models.DateField(
        default=datetime.date(1990, 1, 1),
        help_text='Date of revision'
    )
    latest = models.BooleanField(
        default=True,
        help_text='Is true if this is the latest revision of this book'
    )

    # icon = models.CharField(max_length=10, default='§')

    # JSON fields
    changelog = models.TextField(blank=True, default='[]')
    footnotes = models.TextField(blank=True, default='[]')
    sections = models.TextField(blank=True, default='{}')

    # fussnoten = models.TextField(blank=True)
    # es_fields_exclude = ['revision_date']  # LawBook is not searchable

    class Meta:
        unique_together = (
            ('slug', 'revision_date'),
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
        if isinstance(self.sections, str):
            self.sections = json.loads(self.sections)

        return self.sections

    def get_title(self):
        return self.title

    def get_short_title(self, length=30):
        if len(self.title) < length:
            return self.title
        else:
            return self.title[:length] + ' ...'

    def get_code(self):
        return self.code

    def get_url(self):
        return reverse('laws:book', args=(self.slug,))

    def get_changelog(self):
        if isinstance(self.changelog, str):
            self.changelog = json.loads(self.changelog)

        return self.changelog

    def get_changelog_text(self):
        """
        types: Stand, Hinweis, Sonst

        Format: [{"type":"Stand", "text": "..."}]

        :return:
        """
        ## replace "textlich nachgewiesen, dokumentarisch noch nicht abschließend bearbeitet"
        text = None
        for log in self.get_changelog():
            if log['type'] == 'Stand':
                if text is None:
                    text = log['text']
                else:
                    text += ', ' + log['text']
        return text

    def get_revision_dates(self, limit=0):
        """
        Get a list of available revision dates for this book (in descending order).

        :param limit: Limit the length of returned list
        :return:
        """
        dates = LawBook.objects.filter(code=self.code).order_by('-revision_date').values_list('revision_date', flat=True)

        if limit > 0:
            dates = dates[:limit]

        return dates

    def __str__(self):
        return '%s (%s)' % (self.title, self.revision_date)


class Law(SearchableContent, models.Model):
    """Law model contains actual law text and belongs to a law book"""
    book = models.ForeignKey(
        LawBook,
        on_delete=models.CASCADE,
        help_text='The book this law belongs to'
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='Date of creation of this database entry'
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Last change of database entry'
    )
    text = models.TextField(
        blank=True,
        help_text='Plain text for searching'
    )
    content = models.TextField(
        blank=True,
        help_text='Law content with HTML tags and reference markers'
    )
    title = models.CharField(
        max_length=200,
        default='',
        help_text='Verbose title of law'
    )
    slug = models.SlugField(
        max_length=200,
        help_text='Slug based on section'
    )
    enbez = models.CharField(
        blank=True,
        max_length=200)  # TODO refactor as "section"
    amtabk = models.CharField(
        blank=True,
        null=True,
        max_length=200
    )
    kurzue = models.CharField(
        blank=True,
        null=True,
        max_length=200
    )
    doknr = models.CharField(
        blank=True,
        null=True,
        max_length=200,
        help_text='Document number as in XML source'
    )
    footnotes = models.TextField(
        blank=True,
        null=True,
        help_text='Footnotes as JSON array'
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text='Order within law book'
    )
    previous = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        related_name='previous_law',
        help_text='Points to previous law based on order value'
    )

    # Internal fields (non db)
    reference_markers = None
    references = None

    # Define files that will be excluded in JSON export / Elasticsearch document
    es_fields_exclude = ['content', 'amtabk', 'footnotes', 'doknr']
    es_type = 'law'

    class Meta:
        unique_together = (('book', 'slug'), )

    @staticmethod
    def from_hit(hit):
        # Create book from ES data
        book = LawBook(title=hit['book_title'], code=hit['book_code'], slug=hit['book_slug'], latest=True)

        obj = Law(title=hit['title'], book=book, slug=hit['slug'], text=hit['text'], enbez=hit['enbez'])

        # amtabk=hit['amtabk']

        return obj

    def __str__(self):
        return 'Law(%s §%s, title=%s)' % (self.book.code, self.slug, self.title)

    def get_html_content(self):
        content = self.content

        from oldp.apps.references.models import LawReferenceMarker
        content = LawReferenceMarker.make_markers_clickable(content)

        return content

    def is_disabled(self):
        return self.title == '(weggefallen)' and (self.content == '' or self.content.strip() == '<P/>' or self.content.strip() == '<P>-</P>')

    def get_next(self):
        # if self._next is None:
        return Law.objects.get(previous=self.id)

    # def get_previous_url(self):
    #     pass

    def has_footnotes(self):
        return self.footnotes is not None and self.footnotes != ''

    def has_next(self):
        return self.get_next() is not None
        # return False

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
        return '%s %s %s' % (self.book.code, self.enbez, self.title)

    def get_short_title(self, length=40):
        if len(self.get_title()) < length:
            return self.get_title()
        else:
            return self.get_title()[:length] + ' ...'

    def get_book_title(self):
        raise ValueError('Call book directly')

    def get_section(self):
        return self.book.get_sections().get(str(self.order))

    def get_related(self, n=5):
        """ Related items that are pre-computed with "generate_related_cases" command.

        :param n: number of items
        :return:
        """
        items = []
        for item in RelatedLaw.objects.filter(seed_content=self).order_by('-score')[:n]:
            items.append(item.related_content)
        return items

    def get_url(self):
        return reverse('laws:law', args=(self.book.slug, self.slug,))

    def get_admin_url(self):
        return reverse('admin:laws_law_change', args=(self.pk, ))

    def get_es_url(self):
        return settings.ES_URL + '/law/%s' % self.pk

    def get_references(self):
        if self.references is None:
            from oldp.apps.references.models import LawReference
            self.references = LawReference.objects.filter(marker__referenced_by=self)
        return self.references

    def get_reference_markers(self):
        if self.reference_markers is None:
            from oldp.apps.references.models import LawReferenceMarker
            self.reference_markers = LawReferenceMarker.objects.filter(referenced_by=self.id)
        return self.reference_markers

    def get_search_snippet(self, max_length=100):
        if self.search_snippet is None:
            text = strip_tags(html.unescape(self.content))

            from oldp.apps.references.models import LawReferenceMarker
            text = LawReferenceMarker.remove_markers(text)

            return text[:max_length] + ' ...'
        else:
            return self.search_snippet

    def save_reference_markers(self):
        """
        Save references markers generated by ExtractRefs processing step

        :return: None
        """
        from oldp.apps.references.models import LawReferenceMarker

        if self.reference_markers:
            for ref in self.reference_markers:
                marker = LawReferenceMarker().from_ref(ref, self)
                marker.save()
                marker.set_references(marker.ids)
                marker.save_references()

                # logger.debug('Saved: %s' % marker)
        else:
            # logger.debug('No reference markers to save')
            pass

    def pre_index(self, model_dict) -> dict:
        book = self.book
        model_dict['book_title'] = book.title
        model_dict['book_code'] = book.code
        model_dict['book_slug'] = book.slug
        model_dict['full_slug'] = book.slug + ' ' + self.slug.replace('-', ' ')

        return model_dict


@receiver(pre_save, sender=Law)
def pre_save_law(sender, instance: Law, *args, **kwargs):

    # Convert law content as plain text for ES
    text = strip_tags(html.unescape(instance.content))

    from oldp.apps.references.models import LawReferenceMarker
    instance.text = LawReferenceMarker.remove_markers(text)


class RelatedLaw(RelatedContent):
    seed_content = models.ForeignKey(Law, related_name='seed_id', on_delete=models.CASCADE)
    related_content = models.ForeignKey(Law, related_name='related_id', on_delete=models.CASCADE)
