from django.contrib import admin
from django.contrib.admin import SimpleListFilter

from oldp.apps.processing.admin import ProcessingStepActionsAdmin

from .models import City, Country, Court, State

admin.site.register(Country)
admin.site.register(State)
admin.site.register(City)


class APISubmissionFilter(SimpleListFilter):
    title = "API submission"
    parameter_name = "api_submission"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Created via API"),
            ("no", "Not created via API"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(created_by_token__isnull=True)
        if self.value() == "no":
            return queryset.filter(created_by_token__isnull=True)


@admin.register(Court)
class CourtAdmin(ProcessingStepActionsAdmin):
    ordering = ("name",)
    date_hierarchy = "updated_date"
    list_display = (
        "name",
        "slug",
        "court_type",
        "city",
        "code",
        "updated_date",
        "created_date",
        "created_by_token",
        "review_status",
    )
    list_filter = (
        APISubmissionFilter,
        "review_status",
        "created_by_token",
    )
    list_select_related = ("created_by_token",)
    actions = ["save_court"]
    search_fields = ["name", "slug", "code"]

    def lookup_allowed(self, lookup, value):
        if lookup == "created_date__date":
            return True
        return super().lookup_allowed(lookup, value)

    def save_court(self, request, queryset):
        for item in queryset:
            item.save()

    save_court.short_description = "Re-save"
