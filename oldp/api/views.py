from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from oldp.apps.courts.models import Court, City, State, Country
from oldp.apps.courts.serializers import CourtSerializer, CitySerializer, StateSerializer, CountrySerializer
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.serializers import LawSerializer, LawBookSerializer


class CourtViewSet(viewsets.ModelViewSet):
    queryset = Court.objects.all().order_by('name')
    serializer_class = CourtSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('court_type', 'slug', 'code', 'state_id', 'city_id')


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all().order_by('name')
    serializer_class = CitySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('state_id', )


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all().order_by('name')
    serializer_class = StateSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('country_id', )


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all().order_by('name')
    serializer_class = CountrySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('code', )


class LawViewSet(viewsets.ModelViewSet):
    queryset = Law.objects.all().order_by('order')
    serializer_class = LawSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('book_id', 'book__latest', 'book__revision_date')


class LawBookViewSet(viewsets.ModelViewSet):
    queryset = LawBook.objects.all().order_by('code')
    serializer_class = LawBookSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('slug', 'code', 'latest', 'revision_date')
