from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from oldp.apps.cases.models import Case
from oldp.apps.cases.serializers import CaseSerializer
from oldp.apps.courts.models import Court, City, State, Country
from oldp.apps.courts.serializers import CourtSerializer, CitySerializer, StateSerializer, CountrySerializer
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.serializers import LawSerializer, LawBookSerializer


class CaseViewSet(viewsets.ModelViewSet):
    queryset = Case.get_queryset()
    serializer_class = CaseSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('slug', 'file_number', 'court_id')


class CourtViewSet(viewsets.ModelViewSet):
    queryset = Court.objects.all()
    serializer_class = CourtSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('court_type', 'slug', 'code', 'state_id', 'city_id')


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('state_id', )


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all()
    serializer_class = StateSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('country_id', )


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('code', )


class LawViewSet(viewsets.ModelViewSet):
    queryset = Law.objects.all()
    serializer_class = LawSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('book_id', 'book__latest', 'book__revision_date')


class LawBookViewSet(viewsets.ModelViewSet):
    queryset = LawBook.objects.all()
    serializer_class = LawBookSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('slug', 'code', 'latest', 'revision_date')
