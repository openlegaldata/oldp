from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models.functions import Length
from django.forms import Textarea

from oldp.apps.cases.processing.processing_steps.assign_court import AssignCourt
from oldp.apps.cases.processing.processing_steps.extract_refs import ExtractRefs
from oldp.apps.references.models import CaseReferenceMarker
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
                .annotate(text_len=Length('text')) \
                .filter(text_len__lte=500)
        if self.value() == 'long':
            return queryset \
                .annotate(text_len=Length('text')) \
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
class CaseAdmin(admin.ModelAdmin):
    date_hierarchy = 'updated_date'
    list_display = (case_title, 'source_name', 'date', 'created_date', 'court')
    list_filter = ('source_name', 'court__state', 'private', TextFilter, CourtFilter, )  # court
    actions = ['assign_court', 'extract_refs']

    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows': 10, 'cols': 200})},
    }

    def assign_court(self, request, queryset):
        step = AssignCourt()
        for case in queryset:
            case = step.process(case)
            case.save()
    assign_court.short_description = AssignCourt.description

    def extract_refs(self, request, queryset):
        step = ExtractRefs()
        for case in queryset:
            # Delete old references
            CaseReferenceMarker.objects.filter(referenced_by=case).delete()

            # Extract new refs
            case = step.process(case)
            case.save()

            case.save_reference_markers()

        # exit(1)

    extract_refs.short_description = ExtractRefs.description


