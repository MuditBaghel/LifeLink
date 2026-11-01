"""Forms for creating and filtering blood requests."""

from datetime import date

from django import forms

from accounts.models import CITIES
from core.forms import BootstrapForm, BootstrapModelForm

from .models import BloodRequest


class BloodRequestForm(BootstrapModelForm):
    city = forms.ChoiceField(choices=[(city, city) for city in CITIES])
    required_by = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "min": str(date.today())}),
        label="Blood needed by",
    )

    class Meta:
        model = BloodRequest
        fields = [
            "patient_name",
            "patient_age",
            "blood_group",
            "units_required",
            "hospital_name",
            "hospital_address",
            "city",
            "pincode",
            "required_by",
            "contact_phone",
            "urgency",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Ward or bed number, doctor's instruction, anything the donor should know",
                }
            ),
            "hospital_address": forms.TextInput(attrs={"placeholder": "Street, area, landmark"}),
        }
        labels = {
            "patient_name": "Patient name",
            "units_required": "Units required",
            "hospital_name": "Hospital or blood bank",
            "contact_phone": "Contact number for coordination",
            "notes": "Additional information",
        }

    def __init__(self, *args, lock_emergency=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["units_required"].widget.attrs.update({"min": 1, "max": 10})
        self.fields["patient_age"].widget.attrs.update({"min": 0, "max": 120})
        if lock_emergency:
            self.fields.pop("urgency", None)
        else:
            self.fields["urgency"].help_text = (
                "Emergency requests are shown in a separate queue and notify matching donors at once."
            )

    def clean_required_by(self):
        value = self.cleaned_data["required_by"]
        if value < date.today():
            raise forms.ValidationError("Choose today or a future date.")
        return value

    def clean_units_required(self):
        value = self.cleaned_data["units_required"]
        if value < 1:
            raise forms.ValidationError("At least one unit is required.")
        if value > 10:
            raise forms.ValidationError("Raise separate requests for more than 10 units.")
        return value


class RequestFilterForm(BootstrapForm):
    q = forms.CharField(required=False, label="Search")
    group = forms.ChoiceField(required=False, label="Blood group")
    city = forms.ChoiceField(required=False, label="City")
    urgency = forms.ChoiceField(
        required=False,
        label="Priority",
        choices=[("", "Any priority")] + list(BloodRequest.Urgency.choices),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "Open requests")] + list(BloodRequest.Status.choices),
    )


class ResponseForm(BootstrapForm):
    message = forms.CharField(
        required=False,
        max_length=300,
        label="Message to the recipient",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "When can you reach the hospital? Anything they should arrange?",
            }
        ),
    )
