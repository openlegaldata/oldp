from django.urls import re_path

from . import views

app_name = 'laws'
urlpatterns = [
    re_path(r'^$', views.view_index, name='index'),
    re_path(r'^(?P<char>[-a-zA-Z0-9])/$', views.view_index, name='index_char'),

    re_path(r'^(?P<book_slug>[-a-z0-9]+)/(?P<law_slug>[-a-z0-9]+)$', views.view_law, name='law'),
    re_path(r'^(?P<book_slug>[-a-z0-9]{2,})/$', views.view_book, name='book'),


]

