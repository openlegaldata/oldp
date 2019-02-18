from django.contrib.auth.models import User
from django.forms import model_to_dict
from django.urls import include, path, reverse
from rest_framework import status
from rest_framework.test import APITestCase, URLPatternsTestCase, APIClient

from oldp.apps.annotations.models import AnnotationLabel, CaseAnnotation


class AnnotationsAPITestCase(APITestCase, URLPatternsTestCase):
    fixtures = [
        'users/with_password_unittest.json',  # password=unittest
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
        'cases/cases.json',
        'annotations/labels.json',
    ]

    urlpatterns = [
        path('api/', include('oldp.api.urls')),
    ]

    username = 'test'
    password = 'test'

    dummy_label = AnnotationLabel(
            name='Some label',
            slug='some-label',
            trusted=False,
            private=True,
        )
    dummy_annotation = CaseAnnotation(
        belongs_to_id=1,
        label_id=2,
        value_str='Some annotation value'
    )

    def setUp(self):
        self.user = User.objects.create_user(self.username, 'test@example.com', self.password)

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=User.objects.get(pk=1))

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=User.objects.get(pk=2))

        super().setUp()

    def tearDown(self):
        self.user.delete()
        super().tearDown()

    def test_create_case_annotation(self):
        dummy_data = model_to_dict(self.dummy_annotation)

        res = self.owner_client.post(reverse('caseannotation-list'), data=dummy_data, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created_id = res.data['id']

        # second time -> expect error: duplicated annotation
        res = self.owner_client.post(reverse('caseannotation-list'), data=dummy_data, format='json')
        # print(res.data['label'])
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('label' in res.data, 'Error should be for `label` field')

    def test_create_case_annotation_as_guest(self):
        dummy_data = model_to_dict(self.dummy_annotation)

        res = self.client.post(reverse('caseannotation-list'), data=dummy_data, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_read_as_guest(self):
        # GET list
        res = self.client.get(reverse('annotationlabel-list'), format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)

        # print(res.data['results'])

        # GET public
        res = self.client.get(reverse('annotationlabel-detail', args=(1, )), format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # GET private
        res = self.client.get(reverse('annotationlabel-detail', args=(2,)), format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_as_owner(self):

        res = self.owner_client.get(reverse('annotationlabel-list'), format='json')

        # print(res.data)

        self.assertEqual(len(res.data['results']), 3)

        # GET private
        res = self.owner_client.get(reverse('annotationlabel-detail', args=(2,)), format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_write_as_guest(self):
        # Create
        res = self.client.post(reverse('annotationlabel-list'), data=model_to_dict(self.dummy_label), format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Update
        res = self.client.put(reverse('annotationlabel-detail', args=(2,)))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Delete
        res = self.client.delete(reverse('annotationlabel-detail', args=(2,)))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_write_as_owner(self):
        dummy_data = model_to_dict(self.dummy_label)
        # Create
        res = self.owner_client.post(reverse('annotationlabel-list'), data=dummy_data, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created_id = res.data['id']

        # Partial update
        updated_name = 'Updated name'
        res = self.owner_client.patch(reverse('annotationlabel-detail', args=(created_id,)), data={'name': updated_name}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], updated_name)

        # Delete
        res = self.owner_client.delete(reverse('annotationlabel-detail', args=(created_id,)))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Get to deleted item
        res = self.owner_client.get(reverse('annotationlabel-detail', args=(created_id,)))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
