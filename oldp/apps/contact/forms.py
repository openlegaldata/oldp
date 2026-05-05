import re

from django import forms
from django.utils.translation import gettext_lazy as _

# Cheap heuristic to filter out drive-by spam where the "name" or
# "message" field is a single token (e.g. a URL) with no separators.
# We expose a generic error rather than the exact threshold so it's
# harder for a bot to fit the rule on retry.
_NAME_MIN_WHITESPACES = 1
_MESSAGE_MIN_WHITESPACES = 5


def _require_min_whitespaces(value, minimum):
    """Reject values with fewer than ``minimum`` whitespace characters.

    The error message is intentionally generic — leaking the threshold
    would defeat the anti-spam purpose.
    """
    if value is None:
        return value
    if len(re.findall(r"\s", value)) < minimum:
        raise forms.ValidationError(_("Invalid input."))
    return value


class ContactForm(forms.Form):
    name = forms.CharField(label=_("Full name"), max_length=30)
    email = forms.EmailField(
        max_length=254,
        label=_("Email address"),
    )
    message = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(),
        help_text=_("Write here your message!"),
        label=_("Message"),
    )
    source = forms.CharField(  # A hidden input for internal use
        max_length=50,  # tell from which page the user sent the message
        widget=forms.HiddenInput(),
        required=False,
    )
    captcha = forms.IntegerField(
        label=_("Captcha: Wie viele Monate hat ein Jahr?"), initial=11, required=True
    )

    def clean_name(self):
        return _require_min_whitespaces(
            self.cleaned_data.get("name"), _NAME_MIN_WHITESPACES
        )

    def clean_message(self):
        return _require_min_whitespaces(
            self.cleaned_data.get("message"), _MESSAGE_MIN_WHITESPACES
        )

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        email = cleaned_data.get("email")
        message = cleaned_data.get("message")
        captcha = cleaned_data.get("captcha")

        if not name and not email and not message:
            raise forms.ValidationError(_("You have to write something!"))

        if captcha != 12:
            raise forms.ValidationError(
                _('Sie müssen die Frage unter "Captcha" korrekt beantworten.')
            )


class ReportContentForm(forms.Form):
    source = forms.CharField(
        label=_("Source URL"),
        max_length=50,
        required=True,
        help_text=_("Enter the URL of the page which contains the infringement"),
    )
    subject = forms.ChoiceField(
        label=_("Type of infringement"),
        choices=(
            ("Privacy", _("Privacy")),
            ("Copyright", _("Copyright Infringement")),
            ("Other", _("Other")),
        ),
    )
    name = forms.CharField(
        max_length=30,
        label=_("Full name"),
    )
    email = forms.EmailField(
        max_length=254,
        label=_("Email address"),
    )
    message = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(),
        help_text=_("Please provide more details on your complaint."),
        label=_("Additional information"),
    )

    def clean_name(self):
        return _require_min_whitespaces(
            self.cleaned_data.get("name"), _NAME_MIN_WHITESPACES
        )

    def clean_message(self):
        return _require_min_whitespaces(
            self.cleaned_data.get("message"), _MESSAGE_MIN_WHITESPACES
        )

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        email = cleaned_data.get("email")
        message = cleaned_data.get("message")

        if not name and not email and not message:
            raise forms.ValidationError(_("You have to write something!"))
