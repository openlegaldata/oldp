from unittest import skip

from django.test import LiveServerTestCase


class APIViewsTestCase(LiveServerTestCase):
    fixtures = [
        'laws/laws.json'
    ]

    def test_index(self):
        res = self.client.get('/api/')
        self.assertEqual(res.status_code, 200, 'Invalid status code returned')

    def test_index_laws(self):
        res = self.client.get('/api/laws/')
        self.assertEqual(res.status_code, 200, 'Invalid status code returned')

    def test_schema(self):
        res = self.client.get('/api/schema/')

        self.assertEqual(res.status_code, 200, 'Invalid status code returned')

    @skip
    def test_with_auth(self):
        # #
        # view = CaseViewSet.as_view({'get': 'list'})
        # #
        # # print(res)
        # factory = APIRequestFactory()
        #
        # request = factory.get('/api/')
        # # force_authenticate(request, user=user)
        # response = view(request)
        #
        # print(response)
        pass
