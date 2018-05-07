from rest_framework import serializers

from oldp.apps.courts.models import Court, Country, State, City


class CourtSerializer(serializers.ModelSerializer):
    class Meta:
        model = Court
        fields = ('id', 'name', 'court_type', 'city', 'state', 'code', 'slug', 'description', 'image', 'homepage',
                  'street_address', 'postal_code', 'address_locality', 'telephone', 'fax_number')


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'code')


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ('id', 'name', 'country', 'slug')


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ('id', 'name', 'state')


