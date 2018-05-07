from django.conf.urls import url

from . import views

app_name = 'courts'
urlpatterns = [
    # url(r'^$', views.index, name='index'),
    # url(r'^state/(?P<state_slug>[-a-z0-9]+)/$', views.index, name='index_state'),
    url(r'^$', views.CourtListView.as_view(), name='index'),
    url(r'^state/(?P<state_slug>[-a-z0-9]+)/$', views.CourtListView.as_view(), name='index_state'),

    # url(r'^(?P<court_slug>[-a-z0-9]+)/$', views.detail, name='detail'),
    url(r'^(?P<court_slug>[-a-z0-9]+)/$', views.CourtCasesListView.as_view(), name='detail'),

    #
    # url(r'^(?P<book_slug>[-a-z0-9]+)/(?P<law_slug>[-a-z0-9]+)$', views.law, name='law'),
    # url(r'^(?P<book_slug>[-a-z0-9]{2,})/$', views.book, name='book'),


]