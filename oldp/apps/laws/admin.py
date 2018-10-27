from django.contrib import admin

from oldp.apps.laws.processing.processing_steps.extract_refs import ExtractLawRefs
from oldp.apps.references.models import LawReferenceMarker
from .models import Law, LawBook


@admin.register(LawBook)
class LawBookAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title', 'order')
    list_filter = ('latest', )
    actions = ['extract_refs']
    search_fields = ['title', 'slug']


@admin.register(Law)
class LawAdmin(admin.ModelAdmin):
    # date_hierarchy = 'updated_date'
    list_display = ('slug', 'title', 'book')
    list_filter = ('book', )  # court
    actions = ['extract_refs']

    search_fields = ['book__title', 'book__slug']
    autocomplete_fields = ['book']

    def get_queryset(self, request):
        return super(LawAdmin, self).get_queryset(request).select_related('book')

    def extract_refs(self, request, queryset):
        step = ExtractLawRefs()
        for law in queryset:
            # Delete old references
            LawReferenceMarker.objects.filter(referenced_by=law).delete()

            # Extract new refs
            law = step.process(law)
            law.save()

    extract_refs.short_description = ExtractLawRefs.description

