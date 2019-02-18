from django.contrib import admin

from .models import *


@admin.register(AnnotationLabel)
class AnnotationLabelAdmin(admin.ModelAdmin):
    autocomplete_fields = ['owner']
    search_fields = ['name', 'slug']

    list_display = ('name', 'owner', 'private', 'trusted', )
    list_filter = ('private', 'trusted', )


@admin.register(CaseAnnotation)
class CaseAnnotationAdmin(admin.ModelAdmin):
    autocomplete_fields = ['label', 'belongs_to']

    list_display = ('belongs_to', 'label', 'value', )


@admin.register(CaseMarker)
class CaseMarkerAdmin(admin.ModelAdmin):
    autocomplete_fields = ['label', 'belongs_to']

    list_display = ('belongs_to', 'label', 'value', 'start', 'end' )
