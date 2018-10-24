from django.contrib import admin

from .models import *

admin.site.register(LawReferenceMarker)
admin.site.register(CaseReferenceMarker)

admin.site.register(Reference)

