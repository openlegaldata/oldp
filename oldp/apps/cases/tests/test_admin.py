from django.contrib.admin import AdminSite, ModelAdmin
from django.test import tag, TestCase

from oldp.apps.cases.models import Case


class MockRequest:
    pass


class MockSuperUser:
    def has_perm(self, perm):
        return True


request = MockRequest()
request.user = MockSuperUser()


@tag('admin')
class CasesAdminTestCase(TestCase):
    def setUp(self):
        self.site = AdminSite()

    def test_simple(self):
        """Simple unit tests for model admin"""
        ma = ModelAdmin(Case, self.site)

        fields = ma.get_fields(request)
        form = ma.get_form(request)()

        self.assertIsNotNone(form)
        self.assertIsNotNone(fields)
