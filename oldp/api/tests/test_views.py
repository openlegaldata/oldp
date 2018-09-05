from django.test import LiveServerTestCase


class APIViewsTestCase(LiveServerTestCase):

    def test_index(self):
        # # res = self.client.get('/api/')
        # #
        # view = CaseViewSet.as_view({'get': 'list'})
        # #
        # # self.assertEqual(res.status_code, 200, 'Invalid status code returned')
        # # print(res)
        # factory = APIRequestFactory()
        #
        # request = factory.get('/api/')
        # # force_authenticate(request, user=user)
        # response = view(request)
        #
        # print(response)
        pass
