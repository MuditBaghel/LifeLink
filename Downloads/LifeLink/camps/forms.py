"""Camp administration, feedback and check-in forms."""

from django import forms

from accounts.models import CITIES
from core.forms import BootstrapForm, BootstrapModelForm

from .models import CampFeedback, DonationCamp, VolunteerAssignment


class CampForm(BootstrapModelForm):
    city = forms.ChoiceField(choices=[(city, city) for city in CITIES])

    class Meta:
        model = DonationCamp
        fields = [
            "title",
            "organizer",
            "description",
            "image_url",
            "image_alt",
            "venue",
            "address",
            "city",
            "pincode",
            "starts_at",
            "ends_at",
            "capacity",
            "registration_deadline",
            "contact_phone",
            "status",
        ]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "registration_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self.fields["registration_deadline"].help_text = (
            "Leave blank to close registration when the camp starts."
        )

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "The camp must end after it starts.")
        deadline = cleaned.get("registration_deadline")
        if deadline and starts and deadline > starts:
            self.add_error(
                "registration_deadline", "Registration must close before the camp starts."
            )
        return cleaned


class FeedbackForm(BootstrapForm):
    rating = forms.ChoiceField(
        choices=[(value, f"{value} / 5") for value in range(5, 0, -1)],
        label="Rating",
    )
    comment = forms.CharField(
        required=False,
        label="Comment",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "What should the next camp do better?"}),
    )


class CheckInForm(BootstrapForm):
    token = forms.CharField(
        label="Registration code or token",
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. 9F3C2A1B or paste the QR link", "autofocus": True}
        ),
    )


class VolunteerApplyForm(BootstrapForm):
    duty = forms.ChoiceField(
        choices=VolunteerAssignment.Duty.choices, label="Preferred duty"
    )
    note = forms.CharField(
        required=False, label="Note for the organiser",
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class CampFeedbackAdminFilter(BootstrapForm):
    camp = forms.ChoiceField(required=False, label="Camp")
