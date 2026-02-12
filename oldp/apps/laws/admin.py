from django.contrib import admin

from oldp.apps.processing.admin import ProcessingStepActionsAdmin

from .models import Law, LawBook


@admin.register(LawBook)
class LawBookAdmin(ProcessingStepActionsAdmin):
    change_form_template = "laws/admin/lawbook_change_form.html"
    ordering = ("title",)
    list_display = (
        "slug",
        "title",
        "revision_date",
        "order",
        "updated_date",
        "review_status",
    )
    list_filter = ("latest", "created_by_token", "review_status")
    search_fields = ["title", "slug"]
    autocomplete_fields = ["topics"]

    def lookup_allowed(self, lookup, value):
        if lookup == "created_date__date":
            return True
        return super().lookup_allowed(lookup, value)


@admin.register(Law)
class LawAdmin(ProcessingStepActionsAdmin):
    # date_hierarchy = 'updated_date'
    list_display = ("slug", "title", "book", "review_status")
    list_filter = ("book", "book__latest", "review_status")
    search_fields = ["book__title", "book__slug"]
    autocomplete_fields = ["book"]
    actions = []

    def lookup_allowed(self, lookup, value):
        if lookup == "created_date__date":
            return True
        return super().lookup_allowed(lookup, value)

    def get_queryset(self, request):
        return super(LawAdmin, self).get_queryset(request).select_related("book")
