from django.contrib import admin

from oldp.apps.processing.admin import ProcessingStepActionsAdmin
from .models import *


@admin.register(Reference)
class ReferenceAdmin(ProcessingStepActionsAdmin):
    autocomplete_fields = ['case', 'law']


@admin.register(LawReferenceMarker)
class LawReferenceMarkerAdmin(admin.ModelAdmin):
    autocomplete_fields = ['referenced_by']


@admin.register(CaseReferenceMarker)
class CaseReferenceMarkerAdmin(admin.ModelAdmin):
    autocomplete_fields = ['referenced_by']


