from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models.functions import Length
from django.forms import Textarea

from oldp.apps.processing.admin import ProcessingStepActionsAdmin
from .models import *

admin.site.register(RelatedCase)


def case_title(obj):
    return obj.get_title()


class TextFilter(SimpleListFilter):
    title = 'text' # or use _('country') for translated title
    parameter_name = 'text'

    def lookups(self, request, model_admin):
        return [
            ('short', 'short text (length < 500)'),
            ('long', 'long text (length > 50,000)'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'short':
            return queryset\
                .annotate(text_len=Length('content')) \
                .filter(text_len__lte=500)
        if self.value() == 'long':
            return queryset \
                .annotate(text_len=Length('content')) \
                .filter(text_len__gte=50000)


class CourtFilter(SimpleListFilter):
    title = 'court'  # or use _('country') for translated title
    parameter_name = 'court'

    def lookups(self, request, model_admin):
        return [
            ('known', 'Has court'),
            ('unknown', 'Unknown court'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'known':
            return queryset\
                .exclude(court_id=Court.DEFAULT_ID)
        if self.value() == 'unknown':
            return queryset \
                .filter(court_id=Court.DEFAULT_ID)


@admin.register(Case)
class CaseAdmin(ProcessingStepActionsAdmin):
    date_hierarchy = 'updated_date'
    list_display = (case_title, 'private', 'source', 'date', 'created_date', 'court')
    list_filter = ('source__name', 'private', CourtFilter, )  # court
    # remove filters: 'court__state', TextFilter,
    actions = []
    list_select_related = ('court', )
    autocomplete_fields = ['court', 'preceding_cases', 'following_cases']
    search_fields = ['title', 'slug', 'file_number']
    exclude = []

    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows': 10, 'cols': 200})},
    }

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('court').select_related('source')

        # Exclude fields
        return qs.defer(*Case.defer_fields_list_view)
