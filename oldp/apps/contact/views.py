from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from oldp.apps.contact.forms import ContactForm, ReportContentForm


def form_view(request):
    subject_tpl = 'Contact: %(name)s'
    message_tpl = 'Name: %(name)s\nEmail: %(email)s\nMessage:\n\n%(message)s'

    if request.method == 'POST':
        contact_form = ContactForm(request.POST)

        if contact_form.is_valid():
            subject = subject_tpl % contact_form.cleaned_data
            message = message_tpl % contact_form.cleaned_data

            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [settings.SITE_EMAIL])
            return redirect(reverse('contact:thankyou'))
    else:
        contact_form = ContactForm()

    return render(request, 'contact/form.html', {
        'title': _('Contact'),
        'form': contact_form
    })


def report_content_view(request):
    subject_tpl = 'Reported content: %(name)s'
    message_tpl = 'Subject: %(subject)s\nSource: %(source)s\nName: %(name)s\nEmail: %(email)s\nMessage:\n\n%(message)s'

    if request.method == 'POST':
        form = ReportContentForm(request.POST)

        if form.is_valid():
            subject = subject_tpl % form.cleaned_data
            message = message_tpl % form.cleaned_data

            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [settings.SITE_EMAIL])
            return redirect(reverse('contact:thankyou'))
    else:
        form = ReportContentForm(initial={'source': request.GET.get('source')})

    return render(request, 'contact/report_content.html', {
        'title': _('Report content'),
        'form': form
    })


def thankyou_view(request):
    return render(request, 'contact/thankyou.html', {
        'title': _('Contact'),
    })
