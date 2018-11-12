from django.contrib import admin

from oldp.apps.processing.admin import ProcessingStepActionsAdmin
from .models import Law, LawBook


@admin.register(LawBook)
class LawBookAdmin(ProcessingStepActionsAdmin):
    ordering = ('title', )
    list_display = ('slug', 'title', 'order')
    list_filter = ('latest', )
    search_fields = ['title', 'slug']
    autocomplete_fields = ['topics']


@admin.register(Law)
class LawAdmin(ProcessingStepActionsAdmin):
    # date_hierarchy = 'updated_date'
    list_display = ('slug', 'title', 'book')
    list_filter = ('book__latest', )  # court
    search_fields = ['book__title', 'book__slug']
    autocomplete_fields = ['book']
    actions = []

    def get_queryset(self, request):
        return super(LawAdmin, self).get_queryset(request).select_related('book')
