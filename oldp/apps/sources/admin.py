from django.contrib import admin

from .models import *


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'private']

