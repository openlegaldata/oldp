import django_filters
from django_filters.rest_framework import FilterSet


class AnnotationLabelFilter(FilterSet):
    owner = django_filters.NumberFilter()
    slug = django_filters.CharFilter()
    private = django_filters.BooleanFilter()
    trusted = django_filters.BooleanFilter()


class CaseAnnotationFilter(FilterSet):
    belongs_to = django_filters.NumberFilter()
    label = django_filters.NumberFilter()
