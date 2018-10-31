from django.contrib import admin

from oldp.apps.processing.content_processor import ContentProcessor
from oldp.apps.processing.processing_steps import BaseProcessingStep


def make_processing_action(processing_step: BaseProcessingStep):
    """
    Generate the admin action function for processing steps
    """
    def perform_processing_step(modeladmin, request, queryset):
        for content in queryset:
            processing_step.process(content)
            content.save()

    return perform_processing_step


class ProcessingStepActionsAdmin(admin.ModelAdmin):
    """
    Inherit from this class to add `admin actions` based on processing steps.
    """
    def get_actions(self, request):
        actions = super().get_actions(request)

        cp = ContentProcessor()
        cp.model = self.model

        # Use all available processing steps
        for step_name in cp.get_available_processing_steps():
            step = cp.get_available_processing_steps()[step_name]
            actions[step_name] = (make_processing_action(step),
                                step_name,
                                step.description)
        return actions
