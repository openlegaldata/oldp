from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from oldp.apps.contact.forms import ContactForm

MAIL_SUBJECT = 'LegalResearch contact: %(name)s'
MAIL_MESSAGE = 'Name: %(name)s\nEmail: %(email)s\nMessage:\n\n%(message)s'


def form(request):

    if request.method == 'POST':
        contact_form = ContactForm(request.POST)
        # print('before valid')
        if contact_form.is_valid():
            subject = MAIL_SUBJECT % contact_form.cleaned_data
            message = MAIL_MESSAGE % contact_form.cleaned_data

            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, ['legalresearch@i.mieo.de'])
            return redirect(reverse('contact:thankyou'))
        else:
            pass
            # print('invalid form')
        # print('after valid: %s' % contact_form.errors)
    else:
        contact_form = ContactForm()

    return render(request, 'contact/form.html', {
        'title': _('Contact'),
        'form': contact_form
    })


def thankyou(request):

    return render(request, 'contact/thankyou.html', {
        'title': _('Contact'),
    })
