from oldp.apps.favorites.models import Collection
from oldp.apps.lib.simple_views import SimpleListView, SimpleButton


class CollectionListView(SimpleListView):
    model = Collection
    ordering = ('name', )
    icon = 'fa fa-user'
    template_name = 'simple_views/list.html'
    buttons = [
        SimpleButton('Add', 'favorites:collection_add', 'btn btn-success', 'fa fa-plus'),
    ]
    item_buttons = [
        SimpleButton('Edit', 'favorites:collection_edit', 'btn btn-primary', 'fa fa-pencil'),
        SimpleButton('Delete', 'favorites:collection_delete', 'btn btn-danger', 'fa fa-trash'),
    ]
    list_display = ('name', 'created_date')
