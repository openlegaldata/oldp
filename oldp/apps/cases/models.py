from django.core import serializers
from django.core.serializers.base import DeserializationError
from django.http import HttpRequest
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _

from oldp.apps.annotations.content_models import AnnotationContent
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import *
from oldp.apps.lib.markers import insert_markers
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.content_models import ReferenceContent
from oldp.apps.search.models import RelatedContent, SearchableContent
from oldp.apps.sources.models import SourceContent

logger = logging.getLogger(__name__)


class Case(SourceContent, models.Model, SearchableContent, ReferenceContent, AnnotationContent):
    """
    Model representing court cases (i.e. opinions, decisions, verdicts, ...)
    """
    title = models.CharField(
        max_length=255,
        default='',
        blank=True,
        help_text='Title (currently not used due to copyright issues)'
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        db_index=True,
        help_text='Used to urls (consists of court, date, file number)',
    )
    court = models.ForeignKey(
        Court,
        default=Court.DEFAULT_ID,
        help_text='Responsible court entity',
        on_delete=models.SET_DEFAULT,
    )
    court_raw = models.CharField(
        max_length=255,
        default='{}',
        help_text='Raw court information from crawler (JSON)',
    )
    court_chamber = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text='Court chamber (e.g. 1. Senat)'
    )
    date = models.DateField(
        null=True,
        db_index=True,
        help_text='Publication date as in source'
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='Entry is created at this date time',
        db_index=True,
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Date time of last change',
        db_index=True,
    )
    file_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='File number as defined by court'
    )
    type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Type of decision (Urteil, Beschluss, ...)',
        db_index=True,
    )
    pdf_url = models.URLField(
        # TODO Maybe we should store PDF files locally as well
        null=True,
        blank=True,
        max_length=255,
        help_text='URL to original PDF file (not in use)'
    )
    private = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Private content is hidden in production for non-staff users'
    )
    raw = models.TextField(
        null=True,
        blank=True,
        help_text='Raw content (HTML) from crawler that can used to reconstruct all case information',
        editable=False,
    )
    abstract = RichTextField(
        null=True,
        blank=True,
        help_text='Case abstract (Leitsatz) formatted in HTML'
    )
    content = RichTextField(
        help_text='Case full-text formatted in Legal HTML'
    )
    ecli = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='ECLI',
        help_text='European Case Law Identifier'
    )
    preceding_cases = models.ManyToManyField(
        'self',
        blank=True,
        help_text='Cases from inferior courts (lower judicial authority)'
    )
    preceding_cases_raw = models.TextField(
        blank=True,
        null=True,
        help_text='Cases from inferior courts as in source HTML',
    )
    following_cases = models.ManyToManyField(
        'self',
        blank=True,
        help_text='Cases from superior courts (higher judicial authority)',
    )
    following_cases_raw = models.TextField(
        blank=True,
        null=True,
        help_text='Cases from inferior courts as in source HTML',
    )

    # The following fields are excluded from the SELECT-query when querying the database
    defer_fields_list_view = [
        'court_raw',
        'pdf_url',
        'source_url',
        'source_file',
        'raw',
        'content',
        'preceding_cases',
        'preceding_cases_raw',
        'following_cases',
        'following_cases_raw',
        'court__description',
        'court__homepage',
        'court__image',
        'court__street_address',
        'court__postal_code',
        'court__address_locality',
        'court__telephone',
        'court__fax_number',
        'court__email',
    ]

    class Meta:
        ordering = ('-date', )
        unique_together = (('court', 'file_number'),)
        # TODO court, year, file_number should be better

    def is_private(self):
        """
        Whether this item should be visible to all users in production
        """
        return self.private

    def get_filename(self, ext='json'):
        return '%s.%s' % (self.slug, ext)

    def get_topics(self):
        # TODO
        return _('Unknown topic')

    def get_court_raw(self):
        """
        Court information from source
        """
        return json.loads(self.court_raw)

    def get_type(self):
        return self.__class__.__name__

    def get_id(self):
        return self.id

    def get_content_as_html(self, request=None) -> str:
        """Content is stored in HTML (no conversion needed)

        :return: str
        """

        # TODO make line numbers clickable

        content = self.content

        if content is None or len(content) < 1:
            logger.warning('Content is not set or empty')

        markers = []

        # TODO db should return markers already in order
        markers += list(self.get_reference_markers())

        # Generic markers
        markers += list(self.get_markers(request))

        content = insert_markers(content, markers)

        return content

    def get_text(self) -> str:
        """ Case content as plain text

        :return: plain-text
        """
        return strip_tags(html.unescape(self.content))


    def get_title(self) -> str:

        try:
            court_name = self.court.name

            # Attach chamber if available
            if self.court_chamber is not None and self.court_chamber != '':
                court_name += ' (' + self.court_chamber + ')'
        except Court.DoesNotExist:
            court_name = '(no court)'

        return '%s vom %s - %s' % (self.get_case_type(), court_name, self.file_number)

    def get_short_title(self, max_length=75) -> str:
        title = self.get_title()
        if len(title) > max_length:
            return title[:max_length] + '...'
        else:
            return title

    def get_case_type(self):
        return self.type

    def get_date(self, date_format='%Y-%m-%d'):
        return self.date.strftime(date_format)

    def get_related(self, n=5):
        """
        Related items that are pre-computed with "generate_related_cases" command.

        :param n: number of items
        :return:
        """
        items = []
        for item in RelatedCase.objects.filter(seed_content=self).order_by('-score')[:n]:
            items.append(item.related_content)
        return items

    def get_short_url(self):
        return settings.SITE_URL + reverse('cases_short_url', args=(self.pk,))

    def get_absolute_url(self):
        if self.slug is None or self.slug == '':  # TODO added view by id
            self.slug = 'no-slug'

        return reverse('cases:case', args=(self.slug,))

    def get_api_url(self):
        return '/api/cases/{}/'.format(self.pk)

    def get_admin_url(self):
        return reverse('admin:cases_case_change', args=(self.pk, ))

    def get_es_url(self):
        return settings.ELASTICSEARCH_URL + settings.ELASTICSEARCH_INDEX + '/modelresult/cases.case.%s' % self.pk

    def get_reference_marker_model(self):
        from oldp.apps.references.models import CaseReferenceMarker
        return CaseReferenceMarker

    def set_slug(self):
        # Transform date to string
        if isinstance(self.date, datetime.date):
            date_str = self.date.strftime('%Y-%m-%d')
        else:
            date_str = '%s' % self.date

        # File numbers can be lists, so limit the length
        max_fn_length = 20

        self.slug = self.court.slug + '-' + date_str+ '-' + slugify(self.file_number[:max_fn_length])

    def set_ecli(self):
        """Generate ECLI from court code and file number

        See ECLI definition:

        Consists of:
        - ‘ECLI’: to identify the identifier as being a European Case Law Identifier;
        - the country code;
        - the code of the court that rendered the judgment;
        - the year the judgment was rendered;
        - an ordinal number, up to 25 alphanumeric characters, in a format that is decided upon by each Member State.
            Dots are allowed, but not other punctuation marks.

        """
        self.ecli = 'ECLI:de:' + self.court.code + ':' + str(self.date.year) + ':' + slugify(self.file_number)

    def get_annotation_model(self):
        from oldp.apps.annotations.models import CaseAnnotation
        return CaseAnnotation

    def get_marker_model(self):
        from oldp.apps.annotations.models import CaseMarker
        return CaseMarker

    def __str__(self):
        return '<Case(#%i, court=%s, file_number=%s)>' % (self. pk, self.court.code, self.file_number)

    def to_json(self, file_path=None) -> str:
        json_str = serializers.serialize("json", [self])

        if file_path is not None:
            with open(file_path, 'w') as f:
                f.write(json_str)

        return json_str

    @staticmethod
    def from_json_file(file_path):
        with open(file_path) as f:
            out = serializers.deserialize("json", f.read())  # , ignorenonexistent=True)
            # print(len(out))

            try:
                for o in out:
                    return o.object
            except DeserializationError:
                pass

            raise ProcessingError('Cannot deserialize: %s' % file_path)

        # MySQL utf8mb4 bugfix
        # if instance.raw is not None:
        #     instance.raw = ''.join([char if ord(char) < 128 else '' for char in instance.raw])
        #
        # if instance.text is not None:
        #     instance.text = ''.join([char if ord(char) < 128 else '' for char in instance.text])
        #
        # return instance

    @staticmethod
    def get_queryset(request=None):
        # TODO superuser?
        if settings.DEBUG:
            return Case.objects.all()
        else:
            # production
            # hide private content
            return Case.objects.filter(private=False)


class RelatedCase(RelatedContent):
    seed_content = models.ForeignKey(Case, related_name='seed_id', on_delete=models.CASCADE)
    related_content = models.ForeignKey(Case, related_name='related_id', on_delete=models.CASCADE)


