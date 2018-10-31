from django.contrib import admin

from oldp.apps.topics.models import Topic


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    date_hierarchy = 'updated_date'
    list_display = ('title', 'created_date', 'updated_date')
    search_fields = ['title']
