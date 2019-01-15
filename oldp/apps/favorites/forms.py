from django.forms import ModelForm

from oldp.apps.favorites.models import Collection, Favorite


class CollectionForm(ModelForm):
    class Meta:
        model = Collection
        fields = ['name', 'notes', 'private']


class FavoriteForm(ModelForm):
    class Meta:
        model = Favorite
        fields = ['name', 'notes']
