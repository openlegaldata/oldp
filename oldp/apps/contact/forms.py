from django import forms
from django.utils.translation import ugettext_lazy as _


class ContactForm(forms.Form):
    name = forms.CharField(
        label=_('Full name'),
        max_length=30
    )
    email = forms.EmailField(
        max_length=254,
        label=_('Email address'),
    )
    message = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(),
        help_text=_('Write here your message!'),
        label=_('Message')

    )
    source = forms.CharField(       # A hidden input for internal use
        max_length=50,              # tell from which page the user sent the message
        widget=forms.HiddenInput(),
        required=False
    )

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        email = cleaned_data.get('email')
        message = cleaned_data.get('message')

        if not name and not email and not message:
            raise forms.ValidationError(_('You have to write something!'))


class ReportContentForm(forms.Form):
    source = forms.CharField(
        label=_('Source URL'),
        max_length=50,
        required=True,
        help_text=_('Enter the URL of the page which contains the infringement')
    )
    subject = forms.ChoiceField(
        label=_('Type of infringement'),
        choices=(
            ('Privacy', _('Privacy')),
            ('Copyright', _('Copyright Infringement')),
            ('Other', _('Other')),
        ),
    )
    name = forms.CharField(
        max_length=30,
        label=_('Full name'),
    )
    email = forms.EmailField(
        max_length=254,
        label=_('Email address'),
    )
    message = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(),
        help_text=_('Please provide more details on your complaint.'),
        label=_('Additional information')

    )

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        email = cleaned_data.get('email')
        message = cleaned_data.get('message')

        if not name and not email and not message:
            raise forms.ValidationError(_('You have to write something!'))
