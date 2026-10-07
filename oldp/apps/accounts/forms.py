"""Account forms.

The signup form is wired via ``ACCOUNT_SIGNUP_FORM_CLASS`` (see settings). In
allauth 65.x this class is mixed into both the local and the social signup forms,
and allauth calls its ``signup(request, user)`` hook after the user is created —
so the extra profile fields and the newsletter opt-in are captured on every
signup path (email/password *and* GitHub/Google).
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from oldp.apps.accounts.countries import COUNTRY_CHOICES
from oldp.apps.accounts.models import UserProfile
from oldp.apps.accounts.newsletter import start_double_opt_in


class CustomSignupForm(forms.Form):
    """Extra, all-optional profile fields + newsletter opt-in for signup.

    None of these are required — signup must never be blocked on them (the
    required path stays email/username/password). The data feeds community
    segmentation; the opt-in feeds the double-opt-in newsletter flow.
    """

    organization = forms.CharField(
        label=_("Organization"),
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": _("Company, university, or project (optional)")}
        ),
    )
    role = forms.ChoiceField(
        label=_("How do you use Open Legal Data?"),
        choices=[("", _("— Prefer not to say —"))] + UserProfile.ROLE_CHOICES,
        required=False,
    )
    use_case = forms.CharField(
        label=_("What are you building?"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": _(
                    "Optional: tell us what you plan to do with the data."
                ),
            }
        ),
    )
    newsletter_opt_in = forms.BooleanField(
        label=_(
            "Send me occasional product updates and news by email. "
            "I can unsubscribe at any time."
        ),
        required=False,
        initial=False,
    )

    def signup(self, request, user):
        """Persist the extra fields onto the user's profile.

        Called by allauth after the user has been created (the profile already
        exists via the post_save signal). If the user ticked the opt-in box we
        record a *pending* consent and kick off the double-opt-in email — the
        user does not become a subscriber until they confirm.
        """
        profile = user.profile
        profile.organization = self.cleaned_data.get("organization", "")
        profile.role = self.cleaned_data.get("role", "")
        profile.use_case = self.cleaned_data.get("use_case", "")

        if self.cleaned_data.get("newsletter_opt_in"):
            profile.record_opt_in(UserProfile.CONSENT_SOURCE_SIGNUP)

        # The user just saw these fields on the signup form — don't re-prompt
        # them on next login. Grant the bonus if they filled the profile in.
        profile.mark_enrichment_prompted()
        profile.maybe_grant_enrichment_bonus()

        profile.save()

        if profile.newsletter_opt_in:
            start_double_opt_in(request, profile)


class ProfileForm(forms.ModelForm):
    """Edit the segmentation fields from the dashboard.

    Deliberately excludes the consent fields — newsletter opt-in/out goes
    through its own view so the double-opt-in flow is enforced.
    """

    # Country as a dropdown (stores the ISO 3166-1 alpha-2 code).
    country = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        required=False,
        label=_("Country"),
    )

    class Meta:
        model = UserProfile
        fields = ["display_name", "organization", "role", "use_case", "country"]
        widgets = {
            "use_case": forms.Textarea(attrs={"rows": 3}),
        }


class ProfileEnrichmentForm(ProfileForm):
    """The on-login enrichment prompt: profile fields + newsletter opt-in.

    Reuses the dashboard ProfileForm fields and adds the opt-in checkbox so an
    existing user can complete their profile and subscribe in one step.
    """

    newsletter_opt_in = forms.BooleanField(
        label=_(
            "Send me occasional product updates and news by email. "
            "I can unsubscribe at any time."
        ),
        required=False,
        initial=False,
    )


class AccountDeleteForm(forms.Form):
    """Confirm permanent account deletion by re-typing the username."""

    confirm_username = forms.CharField(
        label=_("Confirm your username"),
        help_text=_("Type your username to permanently delete your account."),
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    def __init__(self, *args, expected_username=None, **kwargs):
        self.expected_username = expected_username
        super().__init__(*args, **kwargs)

    def clean_confirm_username(self):
        value = self.cleaned_data["confirm_username"]
        if value != self.expected_username:
            raise forms.ValidationError(
                _("The username does not match. Your account was not deleted.")
            )
        return value
