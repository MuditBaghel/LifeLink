"""Donation camps, registrations with QR tickets, volunteers and feedback."""

import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class CampQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=DonationCamp.Status.SCHEDULED)

    def upcoming(self):
        return self.published().filter(ends_at__gte=timezone.now()).order_by("starts_at")

    def past(self):
        return self.filter(ends_at__lt=timezone.now()).order_by("-starts_at")


class DonationCamp(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=160)
    organizer = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    image_url = models.URLField(
        blank=True, help_text="Photograph shown on the camp card and detail page."
    )
    image_alt = models.CharField(max_length=180, blank=True)
    venue = models.CharField(max_length=160)
    address = models.CharField(max_length=220)
    city = models.CharField(max_length=80, db_index=True)
    pincode = models.CharField(max_length=10, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveSmallIntegerField(default=60)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.SCHEDULED, db_index=True
    )
    is_demo = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_camps",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CampQuerySet.as_manager()

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("camps:camp_detail", kwargs={"pk": self.pk})

    @property
    def slots_taken(self):
        return self.registrations.filter(
            status__in=CampRegistration.ACTIVE_STATUSES
        ).count()

    @property
    def slots_available(self):
        return max(self.capacity - self.slots_taken, 0)

    @property
    def is_full(self):
        return self.slots_available == 0

    @property
    def fill_percent(self):
        if not self.capacity:
            return 0
        return min(int(round(self.slots_taken / self.capacity * 100)), 100)

    @property
    def is_past(self):
        return self.ends_at < timezone.now()

    @property
    def is_live(self):
        return self.starts_at <= timezone.now() <= self.ends_at

    @property
    def closes_at(self):
        return self.registration_deadline or self.starts_at

    @property
    def is_registration_open(self):
        return (
            self.status == self.Status.SCHEDULED
            and not self.is_past
            and not self.is_full
            and timezone.now() < self.closes_at
        )

    @property
    def registration_state(self):
        if self.status == self.Status.CANCELLED:
            return "Cancelled"
        if self.is_past:
            return "Closed"
        if self.is_full:
            return "Full"
        if timezone.now() >= self.closes_at:
            return "Registration closed"
        return "Open"

    @property
    def registration_chip_class(self):
        return {
            "Open": "chip--ok",
            "Full": "chip--urgent",
            "Closed": "chip--muted",
            "Cancelled": "chip--cancelled",
            "Registration closed": "chip--muted",
        }.get(self.registration_state, "chip--muted")

    @property
    def month_label(self):
        return self.starts_at.strftime("%b")

    @property
    def day_label(self):
        return self.starts_at.strftime("%d")


class CampRegistration(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        CHECKED_IN = "checked_in", "Checked in"
        ATTENDED = "attended", "Attended"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    ACTIVE_STATUSES = [Status.REGISTERED, Status.CHECKED_IN, Status.ATTENDED]

    camp = models.ForeignKey(
        DonationCamp, on_delete=models.CASCADE, related_name="registrations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="camp_registrations"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.REGISTERED
    )
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    registered_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="camp_checkins",
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["camp", "user"], name="unique_camp_registration_per_user"
            )
        ]

    def __str__(self):
        return f"{self.user.display_name} @ {self.camp.title}"

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    @property
    def ticket_code(self):
        return str(self.qr_token).split("-")[0].upper()

    @property
    def ticket_url(self):
        return reverse("camps:ticket", kwargs={"token": str(self.qr_token)})

    @property
    def status_chip_class(self):
        return {
            self.Status.REGISTERED: "chip--info",
            self.Status.CHECKED_IN: "chip--ok",
            self.Status.ATTENDED: "chip--ok",
            self.Status.CANCELLED: "chip--cancelled",
            self.Status.NO_SHOW: "chip--muted",
        }.get(self.status, "chip--muted")


class VolunteerAssignment(models.Model):
    class Duty(models.TextChoices):
        REGISTRATION_DESK = "registration", "Registration desk"
        DONOR_GUIDE = "guide", "Donor guide"
        REFRESHMENTS = "refreshments", "Refreshments"
        LOGISTICS = "logistics", "Logistics"
        AWARENESS = "awareness", "Awareness stall"

    camp = models.ForeignKey(
        DonationCamp, on_delete=models.CASCADE, related_name="volunteer_assignments"
    )
    volunteer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="camp_assignments"
    )
    duty = models.CharField(max_length=20, choices=Duty.choices, default=Duty.REGISTRATION_DESK)
    is_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["duty"]
        constraints = [
            models.UniqueConstraint(
                fields=["camp", "volunteer"], name="unique_volunteer_per_camp"
            )
        ]

    def __str__(self):
        return f"{self.volunteer.display_name} · {self.get_duty_display()}"


class CampFeedback(models.Model):
    camp = models.ForeignKey(
        DonationCamp, on_delete=models.CASCADE, related_name="feedback_entries"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="camp_feedback"
    )
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["camp", "user"], name="unique_feedback_per_user")
        ]

    def __str__(self):
        return f"{self.camp.title} · {self.rating}/5"
