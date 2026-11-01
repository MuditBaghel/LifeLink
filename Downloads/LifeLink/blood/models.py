"""Blood requests, lifecycle events and donor responses."""

from django.conf import settings
from django.db import models
from django.urls import reverse

from accounts.models import BLOOD_GROUP_CHOICES


class BloodRequestQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=BloodRequest.OPEN_STATUSES)

    def emergencies(self):
        return self.open().filter(urgency=BloodRequest.Urgency.EMERGENCY)

    def with_related(self):
        return self.select_related("requester", "requester__recipientprofile")

    def for_city(self, city):
        if not city:
            return self
        return self.filter(city__iexact=city)


class BloodRequest(models.Model):
    class Urgency(models.TextChoices):
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgent"
        EMERGENCY = "emergency", "Emergency"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        SEARCHING = "searching", "Searching for donors"
        POTENTIAL = "potential", "Potential donors identified"
        RESPONSES = "responses", "Responses received"
        COORDINATION = "coordination", "Coordination in progress"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    OPEN_STATUSES = [
        Status.CREATED,
        Status.SEARCHING,
        Status.POTENTIAL,
        Status.RESPONSES,
        Status.COORDINATION,
    ]
    TERMINAL_STATUSES = [Status.FULFILLED, Status.CANCELLED]

    ALLOWED_TRANSITIONS = {
        Status.CREATED: [Status.SEARCHING, Status.CANCELLED],
        Status.SEARCHING: [Status.POTENTIAL, Status.CANCELLED],
        Status.POTENTIAL: [Status.RESPONSES, Status.COORDINATION, Status.CANCELLED],
        Status.RESPONSES: [Status.COORDINATION, Status.FULFILLED, Status.CANCELLED],
        Status.COORDINATION: [Status.FULFILLED, Status.CANCELLED],
        Status.FULFILLED: [],
        Status.CANCELLED: [],
    }

    URGENCY_RANK = {"emergency": 0, "urgent": 1, "normal": 2}

    reference = models.CharField(
        max_length=24, unique=True, null=True, blank=True, editable=False
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blood_requests"
    )
    patient_name = models.CharField(max_length=120)
    patient_age = models.PositiveSmallIntegerField(null=True, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    units_required = models.PositiveSmallIntegerField(default=1)
    units_fulfilled = models.PositiveSmallIntegerField(default=0)
    hospital_name = models.CharField(max_length=150)
    hospital_address = models.CharField(max_length=220)
    city = models.CharField(max_length=80, db_index=True)
    pincode = models.CharField(max_length=10, blank=True)
    required_by = models.DateField()
    contact_phone = models.CharField(max_length=20)
    urgency = models.CharField(
        max_length=12, choices=Urgency.choices, default=Urgency.NORMAL, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED, db_index=True
    )
    notes = models.TextField(blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BloodRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "urgency", "city"])]

    def __str__(self):
        return f"{self.reference or 'REQ'} · {self.blood_group} · {self.hospital_name}"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.reference:
            self.reference = f"REQ-{self.created_at.year}-{self.pk:04d}"
            super().save(update_fields=["reference"])

    def get_absolute_url(self):
        return reverse("blood:request_detail", kwargs={"reference": self.reference})

    # -- derived state -----------------------------------------------------
    @property
    def is_emergency(self):
        return self.urgency == self.Urgency.EMERGENCY

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_fulfilled(self):
        return self.status == self.Status.FULFILLED

    @property
    def units_remaining(self):
        return max(self.units_required - self.units_fulfilled, 0)

    @property
    def response_count(self):
        return self.responses.exclude(status=DonorResponse.Status.WITHDRAWN).count()

    @property
    def confirmed_donor_count(self):
        return self.responses.filter(status=DonorResponse.Status.CONFIRMED).count()

    @property
    def progress_percent(self):
        if self.status == self.Status.FULFILLED:
            return 100
        if self.status == self.Status.CANCELLED:
            return 0
        stages = [
            self.Status.CREATED,
            self.Status.SEARCHING,
            self.Status.POTENTIAL,
            self.Status.RESPONSES,
            self.Status.COORDINATION,
            self.Status.FULFILLED,
        ]
        index = stages.index(self.status) if self.status in stages else 0
        return int(round((index / (len(stages) - 1)) * 100))

    @property
    def lifecycle(self):
        """Steps for the tracking timeline, each with a done/current/upcoming state."""
        stages = [
            (self.Status.CREATED, "Request created"),
            (self.Status.SEARCHING, "Searching for donors"),
            (self.Status.POTENTIAL, "Potential donors identified"),
            (self.Status.RESPONSES, "Responses received"),
            (self.Status.COORDINATION, "Coordination in progress"),
            (self.Status.FULFILLED, "Fulfilled"),
        ]
        if self.status == self.Status.CANCELLED:
            return [
                {"code": code, "label": label, "state": "cancelled"}
                for code, label in stages
            ]
        codes = [code for code, _ in stages]
        current = codes.index(self.status) if self.status in codes else 0
        steps = []
        for index, (code, label) in enumerate(stages):
            state = "done" if index < current else "current" if index == current else "upcoming"
            steps.append({"code": code, "label": label, "state": state})
        return steps

    @property
    def allowed_transitions(self):
        return self.ALLOWED_TRANSITIONS.get(self.status, [])

    @property
    def allowed_transition_choices(self):
        labels = dict(self.Status.choices)
        return [
            {"code": code, "label": labels.get(code, code)}
            for code in self.allowed_transitions
        ]

    def can_transition_to(self, status):
        return status in self.allowed_transitions

    @property
    def is_overdue(self):
        from datetime import date

        return self.is_open and self.required_by < date.today()

    @property
    def urgency_chip_class(self):
        return {
            self.Urgency.EMERGENCY: "chip--emergency",
            self.Urgency.URGENT: "chip--urgent",
            self.Urgency.NORMAL: "chip--normal",
        }.get(self.urgency, "chip--muted")

    @property
    def status_chip_class(self):
        return {
            self.Status.CREATED: "chip--muted",
            self.Status.SEARCHING: "chip--info",
            self.Status.POTENTIAL: "chip--info",
            self.Status.RESPONSES: "chip--normal",
            self.Status.COORDINATION: "chip--normal",
            self.Status.FULFILLED: "chip--ok",
            self.Status.CANCELLED: "chip--cancelled",
        }.get(self.status, "chip--muted")

    @property
    def days_until_needed(self):
        from datetime import date

        return (self.required_by - date.today()).days

    @property
    def needed_label(self):
        days = self.days_until_needed
        if days < 0:
            return f"Overdue by {abs(days)} day{'s' if abs(days) != 1 else ''}"
        if days == 0:
            return "Needed today"
        return f"Needed in {days} day{'s' if days != 1 else ''}"


class RequestStatusEvent(models.Model):
    request = models.ForeignKey(
        BloodRequest, on_delete=models.CASCADE, related_name="events"
    )
    status = models.CharField(max_length=20, choices=BloodRequest.Status.choices)
    note = models.CharField(max_length=220, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.request_id} → {self.status}"

    @property
    def status_label(self):
        return dict(BloodRequest.Status.choices).get(self.status, self.status)

    @property
    def status_chip_class(self):
        return {
            BloodRequest.Status.FULFILLED: "chip--ok",
            BloodRequest.Status.CANCELLED: "chip--cancelled",
            BloodRequest.Status.RESPONSES: "chip--normal",
            BloodRequest.Status.COORDINATION: "chip--normal",
        }.get(self.status, "chip--info")


class DonorResponse(models.Model):
    class Status(models.TextChoices):
        INTERESTED = "interested", "Interested"
        CONFIRMED = "confirmed", "Confirmed"
        DECLINED = "declined", "Declined"
        COMPLETED = "completed", "Donated"
        WITHDRAWN = "withdrawn", "Withdrawn"

    request = models.ForeignKey(
        BloodRequest, on_delete=models.CASCADE, related_name="responses"
    )
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="donor_responses"
    )
    message = models.CharField(max_length=300, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INTERESTED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "donor"], name="unique_response_per_donor"
            )
        ]

    def __str__(self):
        return f"{self.donor.display_name} → {self.request.reference}"

    @property
    def counts_towards_fulfilment(self):
        return self.status in (self.Status.CONFIRMED, self.Status.COMPLETED)

    @property
    def status_chip_class(self):
        return {
            self.Status.INTERESTED: "chip--info",
            self.Status.CONFIRMED: "chip--normal",
            self.Status.COMPLETED: "chip--ok",
            self.Status.DECLINED: "chip--muted",
            self.Status.WITHDRAWN: "chip--cancelled",
        }.get(self.status, "chip--muted")
