from django.contrib import admin

from oldp.apps.processing.admin import ProcessingStepActionsAdmin
from .models import *

admin.site.register(Country)
admin.site.register(State)
admin.site.register(City)


@admin.register(Court)
class CourtAdmin(ProcessingStepActionsAdmin):
    ordering = ('name', )
    date_hierarchy = 'updated_date'
    list_display = ('name', 'slug', 'court_type', 'city', 'code', 'updated_date')
    actions = ['save_court']
    search_fields = ['name', 'slug', 'code']

    def save_court(self, request, queryset):
        for item in queryset:
            item.save()
    save_court.short_description = 'Re-save'
