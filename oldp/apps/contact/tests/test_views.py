from django.core import mail
from django.test import LiveServerTestCase
from django.urls import reverse



class ContactViewsTestCase(LiveServerTestCase):

    def test_form(self):
        res = self.client.get(reverse('contact:form'))

        self.assertTemplateUsed(res, 'contact/form.html')

        self.assertContains(res, 'csrfmiddlewaretoken')

    def test_form_submit(self):
        res = self.client.post(reverse('contact:form'), {
            'name': 'My name',
            'email': 'my@email.com',
            'message': 'My Message'
        })

        self.assertRedirects(res, reverse('contact:thankyou'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue('My name' in mail.outbox[0].subject)

        # self.assertHTMLEqual(res.)

    def test_thank_you(self):
        res = self.client.get(reverse('contact:thankyou'))

        self.assertTemplateUsed(res, 'contact/thankyou.html')
