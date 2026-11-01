"""Verified donation records, certificates and achievements."""

import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class DonationRecord(models.Model):
    """A donation only counts once an administrator verifies it."""

    reference = models.CharField(
        max_length=26, unique=True, null=True, blank=True, editable=False
    )
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="donations"
    )
    camp = models.ForeignKey(
        "camps.DonationCamp",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    request = models.ForeignKey(
        "blood.BloodRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    donation_date = models.DateField()
    units = models.PositiveSmallIntegerField(default=1)
    hospital = models.CharField(max_length=160)
    notes = models.CharField(max_length=240, blank=True)
    verified = models.BooleanField(default=False, db_index=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_donations",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-donation_date"]

    def __str__(self):
        return f"{self.reference or 'Donation'} · {self.donor.display_name}"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.reference:
            self.reference = f"DON-{self.donation_date.year}-{uuid.uuid4().hex[:6].upper()}"
            super().save(update_fields=["reference"])

    @property
    def can_issue_certificate(self):
        return self.verified

    @property
    def certificate(self):
        return getattr(self, "issued_certificate", None)

    @property
    def state_label(self):
        return "Verified" if self.verified else "Awaiting verification"

    @property
    def state_chip_class(self):
        return "chip--ok" if self.verified else "chip--urgent"


class Certificate(models.Model):
    """Issued only for verified donations; the PDF is generated on download."""

    reference = models.CharField(max_length=30, unique=True, editable=False)
    donation = models.OneToOneField(
        DonationRecord, on_delete=models.CASCADE, related_name="issued_certificate"
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_certificates",
    )

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.reference

    @property
    def download_url(self):
        return reverse(
            "donations:certificate_download", kwargs={"reference": self.reference}
        )

    @property
    def verify_url(self):
        return reverse(
            "donations:certificate_verify", kwargs={"reference": self.reference}
        )


class Achievement(models.Model):
    class Criteria(models.TextChoices):
        DONATION_COUNT = "donation_count", "Verified donations"
        CAMP_ATTENDANCE = "camp_attendance", "Camps attended"
        VOLUNTEER_COUNT = "volunteer_count", "Confirmed camp duties"

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=220)
    criteria = models.CharField(max_length=24, choices=Criteria.choices)
    threshold = models.PositiveSmallIntegerField(default=1)
    icon = models.CharField(max_length=40, default="bi-award")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "threshold"]

    def __str__(self):
        return self.name


class DonorAchievement(models.Model):
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="achievements"
    )
    achievement = models.ForeignKey(
        Achievement, on_delete=models.CASCADE, related_name="awards"
    )
    awarded_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["achievement__sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["donor", "achievement"], name="unique_achievement_per_donor"
            )
        ]

    def __str__(self):
        return f"{self.achievement.name} · {self.donor.display_name}"
