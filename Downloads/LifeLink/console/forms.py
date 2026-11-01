"""Console-only forms."""

from django import forms

from accounts.models import CITIES
from core.forms import BootstrapForm


class AnnouncementForm(BootstrapForm):
    audience = forms.ChoiceField(
        choices=[
            ("all", "Everyone on LifeLink"),
            ("donors", "All donors"),
            ("recipients", "All recipients"),
            ("volunteers", "All volunteers"),
            ("city-donors", "Donors in one city"),
        ],
        label="Audience",
    )
    city = forms.ChoiceField(
        choices=[("", "Select a city")] + [(city, city) for city in CITIES],
        required=False,
        label="City (only for city audience)",
    )
    title = forms.CharField(max_length=140, label="Title")
    body = forms.CharField(
        max_length=320,
        label="Message",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "What should people know or do?"}),
    )
    link = forms.CharField(
        max_length=200,
        required=False,
        label="Link (optional)",
        widget=forms.TextInput(attrs={"placeholder": "/requests/ or /camps/"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience") == "city-donors" and not cleaned.get("city"):
            self.add_error("city", "Choose the city for this announcement.")
        return cleaned
