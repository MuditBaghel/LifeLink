"""Accounts: the custom user plus the three role profiles."""

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
BLOOD_GROUP_CHOICES = [(group, group) for group in BLOOD_GROUPS]

CITIES = [
    "Delhi", "Chandigarh", "Phagwara", "Jalandhar", "Ludhiana", "Amritsar",
    "Mohali", "Patiala", "Bathinda", "Hoshiarpur",
]


class User(AbstractUser):
    """A single user table with a role switch, so every role shares auth."""

    class Role(models.TextChoices):
        DONOR = "donor", "Donor"
        RECIPIENT = "recipient", "Recipient"
        ADMIN = "admin", "Administrator"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DONOR)
    phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=80, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    avatar_url = models.URLField(
        blank=True, help_text="Optional photo URL used by demonstration accounts."
    )
    is_demo = models.BooleanField(
        default=False, help_text="Created by the demonstration data command."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        full = self.get_full_name().strip()
        return full or self.username

    @property
    def initials(self):
        parts = [part for part in (self.first_name, self.last_name) if part]
        if parts:
            return "".join(part[0] for part in parts[:2]).upper()
        return (self.username or "LL")[:2].upper()

    @property
    def is_donor(self):
        return self.role == self.Role.DONOR

    @property
    def is_recipient(self):
        return self.role == self.Role.RECIPIENT

    @property
    def is_platform_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def dashboard_url(self):
        if self.is_platform_admin:
            return reverse("console:admin_dashboard")
        if self.is_recipient:
            return reverse("console:recipient_dashboard")
        return reverse("console:donor_dashboard")

    @property
    def donor_profile(self):
        return getattr(self, "donorprofile", None)

    @property
    def recipient_profile(self):
        return getattr(self, "recipientprofile", None)

    @property
    def volunteer_profile(self):
        return getattr(self, "volunteerprofile", None)

    @property
    def blood_group(self):
        return self.donor_profile.blood_group if self.donor_profile else ""


class DonorProfile(models.Model):
    """Donor-specific data. Only non-sensitive fields are ever shown publicly."""

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Prefer not to say"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="donorprofile"
    )
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)
    city = models.CharField(max_length=80, db_index=True)
    area = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    last_donation_date = models.DateField(null=True, blank=True)
    is_available = models.BooleanField(
        default=True, help_text="Donor is currently willing to be contacted."
    )
    is_verified = models.BooleanField(
        default=False, help_text="Profile reviewed by a LifeLink administrator."
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    share_contact = models.BooleanField(
        default=False, help_text="Show phone number on the public donor card."
    )
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        return f"{self.user.display_name} ({self.blood_group})"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    @property
    def next_eligible_date(self):
        if not self.last_donation_date:
            return None
        return self.last_donation_date + timedelta(days=settings.DONATION_INTERVAL_DAYS)

    @property
    def days_until_eligible(self):
        next_date = self.next_eligible_date
        if not next_date:
            return 0
        return max((next_date - date.today()).days, 0)

    @property
    def is_eligible(self):
        return self.days_until_eligible == 0

    @property
    def meets_age_criteria(self):
        age = self.age
        return age is not None and settings.DONOR_MIN_AGE <= age <= settings.DONOR_MAX_AGE

    @property
    def meets_weight_criteria(self):
        return self.weight_kg is not None and self.weight_kg >= settings.MIN_WEIGHT_KG

    @property
    def can_donate(self):
        return self.is_available and self.is_eligible and self.meets_age_criteria

    @property
    def verified_donation_count(self):
        return self.user.donations.filter(verified=True).count()

    @property
    def verified_units(self):
        return (
            self.user.donations.filter(verified=True).aggregate(total=models.Sum("units"))["total"]
            or 0
        )

    @property
    def last_verified_donation(self):
        return self.user.donations.filter(verified=True).order_by("-donation_date").first()


class RecipientProfile(models.Model):
    """Recipient data: an individual, a family member or an organisation."""

    class Kind(models.TextChoices):
        SELF = "self", "For myself"
        FAMILY = "family", "For a family member or friend"
        ORGANISATION = "organisation", "Hospital, NGO or blood bank"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipientprofile"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.FAMILY)
    organisation = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=80, db_index=True)
    address = models.CharField(max_length=200, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.display_name


class VolunteerProfile(models.Model):
    """Camp volunteering. Admin confirms participation camp by camp."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volunteerprofile"
    )
    city = models.CharField(max_length=80)
    phone = models.CharField(max_length=20, blank=True)
    motivation = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Volunteer: {self.user.display_name}"

    @property
    def assignment_count(self):
        return self.user.camp_assignments.filter(is_confirmed=True).count()
