from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from oldp.apps.courts.models import Court, City, State, Country
from oldp.apps.courts.serializers import CourtSerializer, CitySerializer, StateSerializer, CountrySerializer


class CourtViewSet(viewsets.ModelViewSet):
    queryset = Court.objects.all().order_by('name')
    serializer_class = CourtSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('court_type', 'slug', 'code', 'state_id', 'city_id')
    http_method_names = ['get', 'head', 'options']


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all().order_by('name')
    serializer_class = CitySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('state_id', )
    http_method_names = ['get', 'head', 'options']


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all().order_by('name')
    serializer_class = StateSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('country_id', )
    http_method_names = ['get', 'head', 'options']


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all().order_by('name')
    serializer_class = CountrySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('code', )
    http_method_names = ['get', 'head', 'options']
