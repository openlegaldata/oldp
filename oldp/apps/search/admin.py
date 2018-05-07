from django.contrib import admin

#  Register your models here.
from oldp.apps.search.models import SearchQuery


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    date_hierarchy = 'updated_date'
    list_display = ('query', 'counter', 'created_date', 'updated_date')
