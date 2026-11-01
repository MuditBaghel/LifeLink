"""Request lifecycle, donor responses and the notifications they trigger."""

from django.core.exceptions import ValidationError
from django.db import transaction

from notifications.models import Notification
from notifications.services import notify, notify_many

from .matching import find_matching_donors, is_compatible
from .models import BloodRequest, DonorResponse, RequestStatusEvent

LIFECYCLE_CHAIN = [
    BloodRequest.Status.CREATED,
    BloodRequest.Status.SEARCHING,
    BloodRequest.Status.POTENTIAL,
    BloodRequest.Status.RESPONSES,
    BloodRequest.Status.COORDINATION,
    BloodRequest.Status.FULFILLED,
]

RESPONSE_TRANSITIONS = {
    DonorResponse.Status.INTERESTED: {
        DonorResponse.Status.CONFIRMED,
        DonorResponse.Status.DECLINED,
        DonorResponse.Status.WITHDRAWN,
    },
    DonorResponse.Status.CONFIRMED: {
        DonorResponse.Status.COMPLETED,
        DonorResponse.Status.DECLINED,
        DonorResponse.Status.WITHDRAWN,
    },
    DonorResponse.Status.DECLINED: {DonorResponse.Status.WITHDRAWN},
    DonorResponse.Status.COMPLETED: set(),
    DonorResponse.Status.WITHDRAWN: set(),
}

DONOR_RESPONSE_ACTIONS = {
    DonorResponse.Status.INTERESTED: {DonorResponse.Status.CONFIRMED, DonorResponse.Status.WITHDRAWN},
    DonorResponse.Status.CONFIRMED: {DonorResponse.Status.WITHDRAWN},
    DonorResponse.Status.DECLINED: {DonorResponse.Status.WITHDRAWN},
}

RECIPIENT_RESPONSE_ACTIONS = {
    DonorResponse.Status.INTERESTED: {DonorResponse.Status.CONFIRMED, DonorResponse.Status.DECLINED},
    DonorResponse.Status.CONFIRMED: {DonorResponse.Status.COMPLETED, DonorResponse.Status.DECLINED},
}


def log_event(blood_request, status, actor=None, note=""):
    return RequestStatusEvent.objects.create(
        request=blood_request, status=status, actor=actor, note=note
    )


def progress_to(blood_request, target, actor=None, note=""):
    """Move a request forward along its lifecycle, one permitted hop at a time."""
    if target == BloodRequest.Status.CANCELLED:
        return cancel_request(blood_request, actor, note)
    if blood_request.status in BloodRequest.TERMINAL_STATUSES:
        raise ValidationError("A closed request cannot change status.")
    if blood_request.status not in LIFECYCLE_CHAIN or target not in LIFECYCLE_CHAIN:
        raise ValidationError("Unknown lifecycle status.")
    start = LIFECYCLE_CHAIN.index(blood_request.status)
    end = LIFECYCLE_CHAIN.index(target)
    if end <= start:
        raise ValidationError("Requests can only move forward through the lifecycle.")

    for index, step in enumerate(LIFECYCLE_CHAIN[start + 1 : end + 1], start=start + 1):
        if not blood_request.can_transition_to(step):
            raise ValidationError(
                f"Cannot move from {blood_request.get_status_display()} to "
                f"{BloodRequest.Status(step).label}."
            )
        blood_request.status = step
        blood_request.save(update_fields=["status", "updated_at"])
        log_event(blood_request, step, actor, note if step == target else "")
        notify(
            blood_request.requester,
            Notification.Kind.STATUS,
            f"{blood_request.reference} is now {BloodRequest.Status(step).label}",
            f"{blood_request.patient_name} · {blood_request.blood_group} · "
            f"{blood_request.hospital_name}",
            url=blood_request.get_absolute_url(),
            dedupe_key=f"req{blood_request.pk}-status-{step}",
        )
    return blood_request


def notify_matching_donors(blood_request, limit=60):
    """Tell compatible, available and eligible donors about a request."""
    matches = find_matching_donors(blood_request, limit=limit)
    if not matches:
        return 0
    kind = (
        Notification.Kind.EMERGENCY
        if blood_request.is_emergency
        else Notification.Kind.REQUEST
    )
    prefix = "Emergency" if blood_request.is_emergency else "New"
    title = (
        f"{prefix} {blood_request.blood_group} request at {blood_request.hospital_name}"
    )
    body = (
        f"{blood_request.units_required} unit(s) needed in {blood_request.city} "
        f"by {blood_request.required_by:%d %b %Y}."
    )
    return notify_many(
        [match.donor.user for match in matches],
        kind,
        title,
        body,
        url=blood_request.get_absolute_url(),
        dedupe_prefix=f"req{blood_request.pk}-{kind}",
    )


@transaction.atomic
def publish_request(blood_request, actor=None):
    """Push a freshly created request to donors and record the initial matching."""
    progress_to(
        blood_request,
        BloodRequest.Status.SEARCHING,
        actor,
        "Request published to compatible donors",
    )
    notified = notify_matching_donors(blood_request)
    if notified:
        progress_to(
            blood_request,
            BloodRequest.Status.POTENTIAL,
            None,
            f"{notified} potential donor{'s' if notified != 1 else ''} identified",
        )
    return notified


@transaction.atomic
def respond_to_request(blood_request, donor_user, message=""):
    donor = donor_user.donor_profile
    if donor is None:
        raise ValidationError("Create a donor profile before responding to requests.")
    if blood_request.requester_id == donor_user.pk:
        raise ValidationError("You cannot respond to your own request.")
    if not blood_request.is_open:
        raise ValidationError("This request is already closed.")
    if not donor.is_available:
        raise ValidationError(
            "Your profile is set to unavailable. Turn availability on to respond."
        )
    if not is_compatible(donor.blood_group, blood_request.blood_group):
        raise ValidationError(
            f"{donor.blood_group} red cells are not compatible with "
            f"{blood_request.blood_group} patients."
        )
    if not donor.is_eligible:
        raise ValidationError(
            f"You can donate again in {donor.days_until_eligible} day(s). "
            "The 90-day gap protects your health."
        )
    if DonorResponse.objects.filter(request=blood_request, donor=donor_user).exists():
        raise ValidationError("You have already responded to this request.")

    response = DonorResponse.objects.create(
        request=blood_request, donor=donor_user, message=message
    )
    if blood_request.status in (
        BloodRequest.Status.CREATED,
        BloodRequest.Status.SEARCHING,
        BloodRequest.Status.POTENTIAL,
    ):
        progress_to(
            blood_request,
            BloodRequest.Status.RESPONSES,
            donor_user,
            f"{donor_user.display_name} offered to donate",
        )
    notify(
        blood_request.requester,
        Notification.Kind.RESPONSE,
        f"{donor_user.display_name} responded to {blood_request.reference}",
        f"{donor.blood_group} donor from {donor.city}. Open the request to confirm.",
        url=blood_request.get_absolute_url(),
        dedupe_key=f"req{blood_request.pk}-resp-{donor_user.pk}",
    )
    return response


@transaction.atomic
def set_response_status(response, new_status, actor, note=""):
    if new_status not in RESPONSE_TRANSITIONS.get(response.status, set()):
        raise ValidationError(
            f"A response cannot move from {response.get_status_display()} "
            f"to {DonorResponse.Status(new_status).label}."
        )

    is_donor = actor.pk == response.donor_id
    is_requester = actor.pk == response.request.requester_id
    is_admin = actor.is_platform_admin or actor.is_staff
    if not (is_donor or is_requester or is_admin):
        raise ValidationError("You cannot change this response.")

    if is_donor and not is_admin:
        allowed = DONOR_RESPONSE_ACTIONS.get(response.status, set())
    else:
        allowed = RECIPIENT_RESPONSE_ACTIONS.get(response.status, set())
    if new_status not in allowed:
        raise ValidationError("That action is not available for your role.")

    response.status = new_status
    response.save(update_fields=["status", "updated_at"])

    blood_request = response.request
    request_url = blood_request.get_absolute_url()

    if new_status == DonorResponse.Status.CONFIRMED:
        notify(
            blood_request.requester,
            Notification.Kind.RESPONSE,
            f"{response.donor.display_name} confirmed for {blood_request.reference}",
            "Coordinate the hospital visit and mark the donation complete afterwards.",
            url=request_url,
            dedupe_key=f"resp{response.pk}-confirmed",
        )
        notify(
            response.donor,
            Notification.Kind.RESPONSE,
            f"You are confirmed for {blood_request.reference}",
            f"{blood_request.hospital_name}, {blood_request.city}.",
            url=request_url,
            dedupe_key=f"resp{response.pk}-confirmed-donor",
        )
        if blood_request.status == BloodRequest.Status.RESPONSES:
            progress_to(
                blood_request,
                BloodRequest.Status.COORDINATION,
                actor,
                f"{response.donor.display_name} confirmed",
            )

    elif new_status == DonorResponse.Status.COMPLETED:
        from donations.services import record_completed_response

        record_completed_response(response, actor)
        _recalculate_fulfilment(blood_request, actor, note)
        notify(
            response.donor,
            Notification.Kind.DONATION,
            f"Donation recorded for {blood_request.reference}",
            "An administrator will verify it before your certificate is issued.",
            url=request_url,
            dedupe_key=f"resp{response.pk}-completed",
        )

    elif new_status in (
        DonorResponse.Status.DECLINED,
        DonorResponse.Status.WITHDRAWN,
    ):
        notify(
            response.donor if is_requester else blood_request.requester,
            Notification.Kind.RESPONSE,
            f"Response for {blood_request.reference} was {response.get_status_display().lower()}",
            "Open the request to see the current donor list.",
            url=request_url,
            dedupe_key=f"resp{response.pk}-{new_status}",
        )
        _recalculate_fulfilment(blood_request, actor, note)
    return response


def _recalculate_fulfilment(blood_request, actor, note=""):
    completed = blood_request.responses.filter(
        status=DonorResponse.Status.COMPLETED
    ).count()
    blood_request.units_fulfilled = min(completed, blood_request.units_required)
    blood_request.save(update_fields=["units_fulfilled", "updated_at"])
    if (
        blood_request.units_fulfilled >= blood_request.units_required
        and blood_request.status in BloodRequest.OPEN_STATUSES
    ):
        progress_to(
            blood_request,
            BloodRequest.Status.FULFILLED,
            actor,
            note or "Units required were met by confirmed donations",
        )


def cancel_request(blood_request, actor=None, note=""):
    if blood_request.status == BloodRequest.Status.CANCELLED:
        raise ValidationError("This request is already cancelled.")
    if blood_request.status == BloodRequest.Status.FULFILLED:
        raise ValidationError("A fulfilled request cannot be cancelled.")
    blood_request.status = BloodRequest.Status.CANCELLED
    blood_request.save(update_fields=["status", "updated_at"])
    log_event(blood_request, BloodRequest.Status.CANCELLED, actor, note or "Request cancelled")
    for response in blood_request.responses.exclude(status=DonorResponse.Status.COMPLETED):
        notify(
            response.donor,
            Notification.Kind.STATUS,
            f"{blood_request.reference} was cancelled",
            f"The request at {blood_request.hospital_name} is no longer active.",
            url=blood_request.get_absolute_url(),
            dedupe_key=f"req{blood_request.pk}-cancelled-{response.donor_id}",
        )
    return blood_request


def requester_contact_visible(blood_request, viewer):
    """Only the owner, admins and donors that responded can see the phone number."""
    if not viewer or not viewer.is_authenticated:
        return False
    if viewer.pk == blood_request.requester_id:
        return True
    if viewer.is_platform_admin or viewer.is_staff:
        return True
    return blood_request.responses.filter(donor=viewer).exists()
