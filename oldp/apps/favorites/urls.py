from django.conf.urls import url

from oldp.apps.favorites.forms import CollectionForm, FavoriteForm
from oldp.apps.favorites.models import Collection, Favorite
from oldp.apps.favorites.views import CollectionListView
from oldp.apps.lib.simple_views import SimpleUserViews

app_name = 'favorites'

favorite_sv = SimpleUserViews(model=Favorite, form=FavoriteForm, app_name=app_name)
collection_sv = SimpleUserViews(model=Collection, form=CollectionForm, app_name=app_name)

urlpatterns = [
    url(r'^$',CollectionListView.as_view(), name='index'),
    # url(r'^$', sv.list, name='index'),

    url(r'^add/$', collection_sv.add, name='collection_add'),
    url(r'^delete/(?P<item_id>[0-9]+)/$', collection_sv.delete, name='collection_delete'),
    url(r'^edit/(?P<item_id>[0-9]+)/$', collection_sv.edit, name='collection_edit'),

    # url(r'^imprint$', views.imprint, name='imprint'),
    # url(r'^api', views.api, name='api'),
    # url(r'^contact', views.contact, name='contact'),

]
