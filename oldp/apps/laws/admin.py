from django.contrib import admin

from oldp.apps.laws.processing.processing_steps.extract_refs import ExtractRefs
from oldp.apps.references.models import LawReferenceMarker
from .models import Law, LawBook

admin.site.register(LawBook)


@admin.register(Law)
class LawAdmin(admin.ModelAdmin):
    # date_hierarchy = 'updated_date'
    list_display = ('slug', 'title', 'book')
    list_filter = ('book', )  # court
    actions = ['extract_refs']

    def extract_refs(self, request, queryset):
        step = ExtractRefs()
        for law in queryset:
            # Delete old references
            LawReferenceMarker.objects.filter(referenced_by=law).delete()

            # Extract new refs
            law = step.process(law)
            law.save()

            law.save_reference_markers()

    extract_refs.short_description = ExtractRefs.description

