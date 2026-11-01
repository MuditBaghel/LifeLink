"""Camp registration, QR tickets, check-in and feedback rules."""

import base64
from io import BytesIO

import qrcode
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify

from .models import CampFeedback, CampRegistration, DonationCamp, VolunteerAssignment


def register_for_camp(camp, user):
    """Idempotent, capacity-enforced camp registration."""
    if camp.status != DonationCamp.Status.SCHEDULED:
        raise ValidationError("This camp is not open for registration.")
    if camp.is_past:
        raise ValidationError("This camp has already taken place.")
    if timezone.now() >= camp.closes_at:
        raise ValidationError(
            f"Registration closed on {camp.closes_at:%d %b %Y, %H:%M}."
        )

    existing = CampRegistration.objects.filter(camp=camp, user=user).first()
    if existing and existing.is_active:
        raise ValidationError("You are already registered for this camp.")

    with transaction.atomic():
        if camp.is_full:
            raise ValidationError(
                "Every slot at this camp is taken. Try another camp or join the volunteer list."
            )
        if existing:
            existing.status = CampRegistration.Status.REGISTERED
            existing.note = ""
            existing.save(update_fields=["status", "note"])
            registration = existing
        else:
            registration = CampRegistration.objects.create(camp=camp, user=user)

    notify(
        user,
        Notification.Kind.CAMP,
        f"Registered for {camp.title}",
        f"{camp.starts_at:%d %b %Y, %I:%M %p} at {camp.venue}, {camp.city}. "
        "Your QR ticket is ready.",
        url=registration.ticket_url,
        dedupe_key=f"camp{registration.pk}-registered",
    )
    return registration


def cancel_registration(registration, user):
    if registration.user_id != user.pk and not (user.is_platform_admin or user.is_staff):
        raise ValidationError("You can only cancel your own registration.")
    if not registration.is_active:
        raise ValidationError("This registration is already inactive.")
    if registration.camp.is_past:
        raise ValidationError("Past camp registrations cannot be cancelled.")
    registration.status = CampRegistration.Status.CANCELLED
    registration.save(update_fields=["status"])
    notify(
        registration.user,
        Notification.Kind.CAMP,
        f"Registration cancelled for {registration.camp.title}",
        "The slot has been released. You can register again before the deadline.",
        url=registration.camp.get_absolute_url(),
        dedupe_key=f"camp{registration.pk}-cancelled",
    )
    return registration


def find_registration_by_token(token):
    token = (token or "").strip().lower()
    if not token:
        return None
    queryset = CampRegistration.objects.select_related("camp", "user")
    try:
        return queryset.get(qr_token=token)
    except (CampRegistration.DoesNotExist, ValidationError):
        pass
    for registration in queryset:
        if registration.ticket_code.lower() == token:
            return registration
    return None


def check_in(registration, staff_user):
    """Staff check-in. Also records a pending donation for donors present at the camp."""
    if not (staff_user.is_platform_admin or staff_user.is_staff):
        raise ValidationError("Only LifeLink staff can check in a registration.")
    if registration.status == CampRegistration.Status.CANCELLED:
        raise ValidationError("This registration was cancelled.")
    if registration.status in (
        CampRegistration.Status.CHECKED_IN,
        CampRegistration.Status.ATTENDED,
    ):
        raise ValidationError(
            f"Already checked in at {registration.checked_in_at:%d %b %Y, %H:%M}."
        )

    registration.status = CampRegistration.Status.CHECKED_IN
    registration.checked_in_at = timezone.now()
    registration.checked_in_by = staff_user
    registration.save(update_fields=["status", "checked_in_at", "checked_in_by"])

    donation = None
    if registration.user.donor_profile:
        from donations.services import record_donation

        donation = record_donation(
            donor=registration.user,
            donation_date=registration.camp.starts_at.date(),
            units=1,
            hospital=registration.camp.venue,
            camp=registration.camp,
            notes="Recorded at camp check-in, awaiting verification",
        )

    notify(
        registration.user,
        Notification.Kind.CAMP,
        f"Checked in at {registration.camp.title}",
        "Your donation has been recorded. An administrator verifies it before your certificate is issued.",
        url=registration.ticket_url,
        dedupe_key=f"camp{registration.pk}-checkedin",
    )
    return registration, donation


def mark_attended(registration, staff_user):
    registration.status = CampRegistration.Status.ATTENDED
    registration.save(update_fields=["status"])
    return registration


def mark_no_show(registration):
    registration.status = CampRegistration.Status.NO_SHOW
    registration.save(update_fields=["status"])
    return registration


def apply_as_volunteer(camp, user, duty, note=""):
    if camp.is_past:
        raise ValidationError("This camp has already taken place.")
    assignment, created = VolunteerAssignment.objects.get_or_create(
        camp=camp,
        volunteer=user,
        defaults={"duty": duty, "is_confirmed": False},
    )
    if not created:
        if assignment.is_confirmed:
            raise ValidationError("You are already confirmed for this camp.")
        assignment.duty = duty
        assignment.save(update_fields=["duty"])
    notify(
        user,
        Notification.Kind.CAMP,
        f"Volunteer request sent for {camp.title}",
        "An administrator confirms volunteer duties before the camp.",
        url=camp.get_absolute_url(),
        dedupe_key=f"volunteer-{camp.pk}-{user.pk}",
    )
    return assignment


def confirm_assignment(assignment, staff_user, confirmed=True):
    assignment.is_confirmed = confirmed
    assignment.save(update_fields=["is_confirmed"])
    if confirmed:
        from donations.services import award_achievements

        award_achievements(assignment.volunteer)
        notify(
            assignment.volunteer,
            Notification.Kind.CAMP,
            f"Volunteer duty confirmed for {assignment.camp.title}",
            f"Duty: {assignment.get_duty_display()} at {assignment.camp.venue}.",
            url=assignment.camp.get_absolute_url(),
            dedupe_key=f"volunteer-confirmed-{assignment.pk}",
        )
    return assignment


def save_feedback(camp, user, rating, comment=""):
    if not camp.is_past and not camp.is_live:
        raise ValidationError("Feedback opens once the camp has started.")
    feedback, created = CampFeedback.objects.update_or_create(
        camp=camp,
        user=user,
        defaults={"rating": rating, "comment": comment},
    )
    return feedback, created


def qr_data_uri(payload):
    """PNG QR code as a data URI, rendered locally with no external service."""
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=7,
        border=2,
    )
    code.add_data(payload)
    code.make(fit=True)
    image = code.make_image(fill_color="#14243A", back_color="#FFFFFF")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def ticket_qr(registration, request=None):
    path = reverse("camps:checkin_scan", kwargs={"token": str(registration.qr_token)})
    payload = request.build_absolute_uri(path) if request else path
    return qr_data_uri(payload)
