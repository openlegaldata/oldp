from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db import models
from django.db.models.functions import Length
from django.forms import Textarea
from django.utils import timezone

from oldp.apps.processing.admin import ProcessingStepActionsAdmin

from .models import Case, Court, RelatedCase

admin.site.register(RelatedCase)


def case_title(obj):
    return obj.get_title()


class TextFilter(SimpleListFilter):
    title = "text"  # or use _('country') for translated title
    parameter_name = "text"

    def lookups(self, request, model_admin):
        return [
            ("short", "short text (length < 500)"),
            ("long", "long text (length > 50,000)"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "short":
            return queryset.annotate(text_len=Length("content")).filter(
                text_len__lte=500
            )
        if self.value() == "long":
            return queryset.annotate(text_len=Length("content")).filter(
                text_len__gte=50000
            )


class CourtFilter(SimpleListFilter):
    title = "court"  # or use _('country') for translated title
    parameter_name = "court"

    def lookups(self, request, model_admin):
        return [
            ("known", "Has court"),
            ("unknown", "Unknown court"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "known":
            return queryset.exclude(court_id=Court.DEFAULT_ID)
        if self.value() == "unknown":
            return queryset.filter(court_id=Court.DEFAULT_ID)


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


@admin.register(Case)
class CaseAdmin(ProcessingStepActionsAdmin):
    date_hierarchy = "updated_date"
    list_display = (
        case_title,
        "review_status",
        "source",
        "date",
        "created_date",
        "court",
        "created_by_token",
    )
    list_filter = (
        "source__name",
        "review_status",
        APISubmissionFilter,
        CourtFilter,
    )  # court
    # remove filters: 'court__state', TextFilter,
    actions = ["takedown_cases", "clear_moderation"]
    list_select_related = ("court",)
    readonly_fields = ("moderated_at",)
    autocomplete_fields = ["court", "preceding_cases", "following_cases"]
    search_fields = ["title", "slug", "file_number"]
    exclude = []

    formfield_overrides = {
        models.TextField: {"widget": Textarea(attrs={"rows": 10, "cols": 200})},
    }

    def lookup_allowed(self, lookup, value):
        if lookup == "created_date__date":
            return True
        return super().lookup_allowed(lookup, value)

    @admin.action(description="Takedown: hide from all channels and purge text")
    def takedown_cases(self, request, queryset):
        """Privacy/takedown action — see docs/content-moderation.md.

        Hides the selected cases (review_status=rejected), blanks the stored
        text and records the moderator and time. The reason / report reference
        is added afterwards in the ``moderation_note`` field of the change form.
        Cases are saved one by one so the post-save signals drop the search
        index document and the view cache.
        """
        count = 0
        for case in queryset:
            case.apply_takedown(
                note=f"Takedown via admin by {request.user} on {timezone.now():%Y-%m-%d}"
            )
            case.save()
            count += 1
        self.message_user(
            request,
            f"{count} case(s) hidden and purged; add the report reference to moderation_note.",
        )

    @admin.action(description="Clear moderation record (allows re-acceptance)")
    def clear_moderation(self, request, queryset):
        """Deliberate way back after a false report. Does not change review_status."""
        count = 0
        for case in queryset:
            case.moderation_note = (
                f"{case.moderation_note}\nModeration cleared by {request.user} on {timezone.now():%Y-%m-%d}"
            ).strip()
            case.moderated_at = None
            case.save(update_fields=["moderated_at", "moderation_note", "updated_date"])
            count += 1
        self.message_user(request, f"Moderation record cleared on {count} case(s).")

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related("court")
            .select_related("source")
            .select_related("created_by_token")
        )

        # Exclude fields
        return qs.defer(*Case.defer_fields_list_view)
