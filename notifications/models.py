"""In-app notifications with per-user preferences and duplicate protection."""

from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    class Kind(models.TextChoices):
        REQUEST = "request", "Blood request"
        EMERGENCY = "emergency", "Emergency request"
        RESPONSE = "response", "Donor response"
        STATUS = "status", "Request status"
        CAMP = "camp", "Donation camp"
        DONATION = "donation", "Donation"
        CERTIFICATE = "certificate", "Certificate"
        ACHIEVEMENT = "achievement", "Achievement"
        SYSTEM = "system", "Announcement"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=140)
    body = models.CharField(max_length=320, blank=True)
    url = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    dedupe_key = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"],
                condition=~Q(dedupe_key=""),
                name="unique_notification_per_user_key",
            )
        ]

    def __str__(self):
        return f"{self.user.display_name} · {self.title}"

    @property
    def icon(self):
        return {
            self.Kind.EMERGENCY: "bi-exclamation-octagon-fill",
            self.Kind.REQUEST: "bi-droplet-half",
            self.Kind.RESPONSE: "bi-person-check",
            self.Kind.STATUS: "bi-arrow-repeat",
            self.Kind.CAMP: "bi-calendar2-event",
            self.Kind.DONATION: "bi-clipboard2-pulse",
            self.Kind.CERTIFICATE: "bi-patch-check",
            self.Kind.ACHIEVEMENT: "bi-award",
            self.Kind.SYSTEM: "bi-megaphone",
        }.get(self.kind, "bi-bell")


class NotificationPreference(models.Model):
    """Which notification kinds a user wants to receive in the app."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    matching_requests = models.BooleanField(default=True)
    emergency_requests = models.BooleanField(default=True)
    donor_responses = models.BooleanField(default=True)
    request_updates = models.BooleanField(default=True)
    camp_updates = models.BooleanField(default=True)
    donation_updates = models.BooleanField(default=True)

    def __str__(self):
        return f"Preferences for {self.user.display_name}"

    def allows(self, kind):
        mapping = {
            Notification.Kind.REQUEST: self.matching_requests,
            Notification.Kind.EMERGENCY: self.emergency_requests,
            Notification.Kind.RESPONSE: self.donor_responses,
            Notification.Kind.STATUS: self.request_updates,
            Notification.Kind.CAMP: self.camp_updates,
            Notification.Kind.DONATION: self.donation_updates,
            Notification.Kind.CERTIFICATE: self.donation_updates,
            Notification.Kind.ACHIEVEMENT: self.donation_updates,
        }
        return mapping.get(kind, True)
