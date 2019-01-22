from django.contrib import admin, messages

from oldp.apps.processing.content_processor import ContentProcessor
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.processing.processing_steps import BaseProcessingStep


def make_processing_action(processing_step: BaseProcessingStep):
    """
    Generate the admin action function for processing steps
    """
    def perform_processing_step(modeladmin, request, queryset):
        last_error = None
        last_content = None
        error_counter = 0
        success_counter = 0

        for content in queryset:
            try:
                processing_step.process(content)
                content.save()

                success_counter += 1
            except ProcessingError as e:
                error_counter += 1
                last_error = e
                last_content = content

        # Show results as messages
        stats_msg = ' [Valid: %i; Errors: %i]' % (success_counter, error_counter)

        if error_counter > 0:
            modeladmin.message_user(request, 'Error occurred with %s (last item): %s%s' % (last_content, last_error, stats_msg), level=messages.ERROR)
        else:
            modeladmin.message_user(request, 'Processing completed. ' + stats_msg, level=messages.INFO)

    return perform_processing_step


class ProcessingStepActionsAdmin(admin.ModelAdmin):
    change_form_template = 'processing/admin/change_form.html'
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
