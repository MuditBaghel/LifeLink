"""Registration, login and profile forms."""

from datetime import date

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password

from core.forms import BootstrapForm, BootstrapModelForm

from .models import (
    BLOOD_GROUP_CHOICES,
    CITIES,
    DonorProfile,
    RecipientProfile,
    User,
    VolunteerProfile,
)


class RegistrationForm(BootstrapForm):
    first_name = forms.CharField(max_length=60, label="First name")
    last_name = forms.CharField(max_length=60, label="Last name")
    username = forms.CharField(
        max_length=60,
        label="Username",
        help_text="Used to sign in. Letters, digits and @/./+/-/_ only.",
    )
    email = forms.EmailField(label="Email address")
    phone = forms.CharField(max_length=20, label="Phone number")
    city = forms.ChoiceField(choices=[(city, city) for city in CITIES], label="City")
    role = forms.ChoiceField(
        choices=[
            (User.Role.DONOR, "I want to donate blood"),
            (User.Role.RECIPIENT, "I need blood for a patient"),
        ],
        label="I am registering as",
        widget=forms.RadioSelect,
    )
    blood_group = forms.ChoiceField(
        choices=[("", "Select blood group")] + BLOOD_GROUP_CHOICES,
        required=False,
        label="Blood group",
    )
    date_of_birth = forms.DateField(
        required=False,
        label="Date of birth",
        widget=forms.DateInput(attrs={"type": "date", "max": str(date.today())}),
    )
    gender = forms.ChoiceField(
        choices=[("", "Select")] + list(DonorProfile.Gender.choices),
        required=False,
        label="Gender",
    )
    weight_kg = forms.IntegerField(
        required=False, min_value=30, max_value=200, label="Weight (kg)"
    )
    password1 = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    terms = forms.BooleanField(
        label="I understand that compatibility shown here is preliminary guidance and not medical approval.",
        error_messages={"required": "Please acknowledge the medical disclaimer."},
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The two passwords do not match.")
        if password1:
            validate_password(password1)
        if cleaned.get("role") == User.Role.DONOR:
            if not cleaned.get("blood_group"):
                self.add_error("blood_group", "Donors must select a blood group.")
            dob = cleaned.get("date_of_birth")
            if not dob:
                self.add_error("date_of_birth", "Donors must add a date of birth.")
            else:
                age = (
                    date.today().year
                    - dob.year
                    - ((date.today().month, date.today().day) < (dob.month, dob.day))
                )
                if age < settings.DONOR_MIN_AGE:
                    self.add_error(
                        "date_of_birth",
                        f"Donors must be at least {settings.DONOR_MIN_AGE} years old.",
                    )
                if age > settings.DONOR_MAX_AGE:
                    self.add_error(
                        "date_of_birth",
                        f"Donor registrations are limited to {settings.DONOR_MAX_AGE} years of age.",
                    )
        return cleaned

    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password1"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=data["phone"],
            city=data["city"],
            role=data["role"],
        )
        if user.role == User.Role.DONOR:
            DonorProfile.objects.create(
                user=user,
                blood_group=data["blood_group"],
                date_of_birth=data.get("date_of_birth"),
                gender=data.get("gender") or "",
                weight_kg=data.get("weight_kg"),
                city=data["city"],
            )
        else:
            RecipientProfile.objects.create(user=user, city=data["city"])
        return user


class LoginForm(BootstrapForm):
    username = forms.CharField(
        label="Username", widget=forms.TextInput(attrs={"autofocus": True})
    )
    password = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get("username")
        password = cleaned.get("password")
        if username and password:
            self.user = authenticate(self.request, username=username, password=password)
            if self.user is None:
                raise forms.ValidationError("Username or password is incorrect.")
            if not self.user.is_active:
                raise forms.ValidationError("This account has been disabled.")
        return cleaned

    def get_user(self):
        return self.user


class AccountForm(BootstrapModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "city", "avatar"]
        widgets = {"avatar": forms.FileInput(attrs={"accept": "image/*"})}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email


class DonorProfileForm(BootstrapModelForm):
    city = forms.ChoiceField(choices=[(city, city) for city in CITIES])

    class Meta:
        model = DonorProfile
        fields = [
            "blood_group",
            "date_of_birth",
            "gender",
            "weight_kg",
            "city",
            "area",
            "pincode",
            "last_donation_date",
            "is_available",
            "share_contact",
            "bio",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date", "max": str(date.today())}),
            "last_donation_date": forms.DateInput(attrs={"type": "date", "max": str(date.today())}),
            "bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Availability, preferred hospitals, languages you speak"}),
        }

    def clean_last_donation_date(self):
        value = self.cleaned_data.get("last_donation_date")
        if value and value > date.today():
            raise forms.ValidationError("The last donation date cannot be in the future.")
        return value

    def clean_date_of_birth(self):
        value = self.cleaned_data.get("date_of_birth")
        if value:
            age = (
                date.today().year
                - value.year
                - ((date.today().month, date.today().day) < (value.month, value.day))
            )
            if age < settings.DONOR_MIN_AGE:
                raise forms.ValidationError(
                    f"Donors must be at least {settings.DONOR_MIN_AGE} years old."
                )
        return value


class RecipientProfileForm(BootstrapModelForm):
    city = forms.ChoiceField(choices=[(city, city) for city in CITIES])

    class Meta:
        model = RecipientProfile
        fields = ["kind", "organisation", "city", "address", "pincode"]


class VolunteerProfileForm(BootstrapModelForm):
    city = forms.ChoiceField(choices=[(city, city) for city in CITIES])

    class Meta:
        model = VolunteerProfile
        fields = ["city", "phone", "motivation", "is_active"]
        widgets = {"motivation": forms.Textarea(attrs={"rows": 3})}
