from django.conf.urls import url

from . import views

app_name = 'laws'
urlpatterns = [
    url(r'^$', views.view_index, name='index'),
    url(r'^(?P<char>[-a-zA-Z0-9])/$', views.view_index, name='index_char'),

    url(r'^(?P<book_slug>[-a-z0-9]+)/(?P<law_slug>[-a-z0-9]+)$', views.view_law, name='law'),
    url(r'^(?P<book_slug>[-a-z0-9]{2,})/$', views.view_book, name='book'),


]

