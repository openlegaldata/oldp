from django.urls import include, path
from rest_framework import status
from rest_framework.test import APITestCase, URLPatternsTestCase


class AccountTests(APITestCase, URLPatternsTestCase):
    urlpatterns = [
        path('api/', include('oldp.api.urls')),
    ]

    def test_index(self):
        """
        Ensure we can create a new account object.
        """
        # url = reverse('api/')
        response = self.client.get('/api/cases/', format='json')

        print(response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


