from django.contrib.auth.models import User
from django.test import tag, Client
from django.urls import reverse

from oldp.apps.cases.models import Case
from oldp.apps.lib.tests import ExtendedLiveServerTestCase


@tag('views')
class CasesViewsTestCase(ExtendedLiveServerTestCase):
    fixtures = [
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
        'cases/cases.json'
    ]
    username = 'test'
    password = 'test'

    def setUp(self):
        self.user = User.objects.create_user(self.username, 'test@example.com', self.password)

        self.user_client = Client()
        self.user_client.force_login(self.user)

        self.staff_user = User.objects.create_user('staff', 'staff@example.com', 'staff', is_staff=True)

        self.staff_client = Client()
        self.staff_client.force_login(self.staff_user)


    def test_index(self):
        res = self.client.get(reverse('cases:index'))

        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'another-awesome-case')
        self.assertContains(res, 'foo-case')

        self.assertStringOrder(res, 'foo-case', 'another-awesome-case')

    def test_index_filter(self):
        res = self.client.get(reverse('cases:index') + '?court__state=1')

        self.assertNotContains(res, 'another-awesome-case')
        self.assertContains(res, 'foo-case')

    def test_detail(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_absolute_url())

        self.assertContains(res, item.get_content_as_html(), count=1, status_code=200)

    def test_private_detail(self):

        private_item = Case.objects.get(pk=2)
        res = self.client.get(private_item.get_absolute_url())

        self.assertEqual(404, res.status_code, 'Private content should not be found')

        res = self.staff_client.get(private_item.get_absolute_url())
        self.assertEqual(404, res.status_code, 'Private content should return not found also for staff users')

    def test_detail_as_user(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_absolute_url())
        res_staff = self.staff_client.get(item.get_absolute_url())

        anon_content = item.get_content_as_html(request=res.wsgi_request)
        user_content = item.get_content_as_html(request=res_staff.wsgi_request)

        self.assertContains(res, anon_content, count=1, status_code=200)
        self.assertEqual(anon_content, user_content, 'User and anon content should match (no user content available)')

        # TODO Check on user annotations
        # self.assertContains(res, user_content, count=0, status_code=200)

    def test_short_url(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_short_url())

        self.assertRedirects(res, item.get_absolute_url(), status_code=301)
