"""Public request ledger plus the create, respond and track workflows."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, When
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import BLOOD_GROUPS, CITIES
from core.content import MEDICAL_DISCLAIMER

from . import services
from .forms import BloodRequestForm, ResponseForm
from .matching import donor_pool_summary, find_matching_donors, is_compatible
from .models import BloodRequest, DonorResponse


def _base_queryset():
    return BloodRequest.objects.with_related()


def request_list(request):
    queryset = _base_queryset()
    query = request.GET.get("q", "").strip()
    group = request.GET.get("group", "").strip()
    city = request.GET.get("city", "").strip()
    urgency = request.GET.get("urgency", "").strip()
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "open")

    if scope == "all":
        queryset = queryset.all()
    elif status:
        queryset = queryset.filter(status=status)
    else:
        queryset = queryset.open()

    if query:
        queryset = queryset.filter(
            Q(patient_name__icontains=query)
            | Q(hospital_name__icontains=query)
            | Q(reference__icontains=query)
            | Q(city__icontains=query)
        )
    if group in BLOOD_GROUPS:
        queryset = queryset.filter(blood_group=group)
    if city:
        queryset = queryset.filter(city__iexact=city)
    if urgency:
        queryset = queryset.filter(urgency=urgency)

    urgency_rank = Case(
        When(urgency=BloodRequest.Urgency.EMERGENCY, then=0),
        When(urgency=BloodRequest.Urgency.URGENT, then=1),
        default=2,
        output_field=IntegerField(),
    )
    queryset = queryset.annotate(urgency_rank=urgency_rank).order_by(
        "urgency_rank", "required_by", "-created_at"
    )

    paginator = Paginator(queryset, 10)
    page = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(
        request,
        "blood/request_list.html",
        {
            "page": page,
            "total": paginator.count,
            "groups": BLOOD_GROUPS,
            "cities": CITIES,
            "filters": {
                "q": query,
                "group": group,
                "city": city,
                "urgency": urgency,
                "status": status,
                "scope": scope,
            },
            "querystring": querystring.urlencode(),
            "disclaimer": MEDICAL_DISCLAIMER,
            "emergency_count": BloodRequest.objects.emergencies().count(),
            "urgent_count": BloodRequest.objects.open()
            .filter(urgency=BloodRequest.Urgency.URGENT)
            .count(),
        },
    )


def request_detail(request, reference):
    blood_request = get_object_or_404(_base_queryset(), reference=reference)
    viewer = request.user
    is_owner = viewer.is_authenticated and viewer.pk == blood_request.requester_id
    is_admin = viewer.is_authenticated and (
        viewer.is_platform_admin or viewer.is_staff
    )
    can_manage = is_owner or is_admin

    my_response = None
    can_respond = False
    respond_blocked_reason = ""
    if viewer.is_authenticated and viewer.donor_profile:
        my_response = blood_request.responses.filter(donor=viewer).first()
        donor = viewer.donor_profile
        if my_response:
            can_respond = False
        elif is_owner:
            respond_blocked_reason = "This is your own request."
        elif not blood_request.is_open:
            respond_blocked_reason = "This request is closed."
        elif not donor.is_available:
            respond_blocked_reason = "Set your availability on to respond."
        elif not donor.is_eligible:
            respond_blocked_reason = (
                f"You can donate again in {donor.days_until_eligible} day(s)."
            )
        elif not is_compatible(donor.blood_group, blood_request.blood_group):
            respond_blocked_reason = (
                f"{donor.blood_group} is not compatible with {blood_request.blood_group}."
            )
        else:
            can_respond = blood_request.is_open

    matching = find_matching_donors(blood_request, limit=8) if can_manage else []
    responses = blood_request.responses.select_related("donor", "donor__donorprofile")
    if not can_manage:
        responses = responses.filter(donor=viewer) if viewer.is_authenticated else responses.none()

    return render(
        request,
        "blood/request_detail.html",
        {
            "blood_request": blood_request,
            "is_owner": is_owner,
            "can_manage": can_manage,
            "matching": matching,
            "pool": donor_pool_summary(blood_request) if can_manage else None,
            "responses": responses,
            "my_response": my_response,
            "can_respond": can_respond,
            "respond_blocked_reason": respond_blocked_reason,
            "response_form": ResponseForm(),
            "contact_visible": services.requester_contact_visible(blood_request, viewer),
            "events": blood_request.events.select_related("actor"),
            "disclaimer": MEDICAL_DISCLAIMER,
            "response_statuses": DonorResponse.Status,
        },
    )


def _save_request(request, lock_emergency=False, template="blood/request_form.html"):
    form = BloodRequestForm(request.POST or None, lock_emergency=lock_emergency)
    if request.method == "POST" and form.is_valid():
        blood_request = form.save(commit=False)
        blood_request.requester = request.user
        if lock_emergency:
            blood_request.urgency = BloodRequest.Urgency.EMERGENCY
        blood_request.save()
        services.log_event(
            blood_request, BloodRequest.Status.CREATED, request.user, "Request created"
        )
        notified = services.publish_request(blood_request, request.user)
        if notified:
            messages.success(
                request,
                f"Request {blood_request.reference} is live. {notified} matching donor"
                f"{'s were' if notified != 1 else ' was'} notified.",
            )
        else:
            messages.warning(
                request,
                f"Request {blood_request.reference} is live, but no compatible donor is "
                "available right now. Administrators can see it in the request queue.",
            )
        return redirect(blood_request.get_absolute_url())
    if request.method == "POST":
        messages.error(request, "Please correct the highlighted fields.")
    return render(
        request,
        template,
        {
            "form": form,
            "lock_emergency": lock_emergency,
            "disclaimer": MEDICAL_DISCLAIMER,
        },
    )


@login_required
def request_create(request):
    return _save_request(request)


@login_required
def sos_create(request):
    return _save_request(request, lock_emergency=True, template="blood/sos_form.html")


@login_required
def request_update(request, reference):
    blood_request = get_object_or_404(_base_queryset(), reference=reference)
    if not (request.user.pk == blood_request.requester_id
            or request.user.is_platform_admin):
        messages.error(request, "Only the requester can edit this request.")
        return redirect(blood_request.get_absolute_url())
    if not blood_request.is_open:
        messages.error(request, "Closed requests cannot be edited.")
        return redirect(blood_request.get_absolute_url())

    form = BloodRequestForm(
        request.POST or None,
        instance=blood_request,
        lock_emergency=blood_request.is_emergency,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        services.log_event(
            blood_request, blood_request.status, request.user, "Request details updated"
        )
        messages.success(request, "Request updated.")
        return redirect(blood_request.get_absolute_url())
    return render(
        request,
        "blood/request_form.html",
        {"form": form, "blood_request": blood_request, "lock_emergency": blood_request.is_emergency},
    )


@login_required
def request_cancel(request, reference):
    blood_request = get_object_or_404(_base_queryset(), reference=reference)
    if not (request.user.pk == blood_request.requester_id
            or request.user.is_platform_admin):
        messages.error(request, "Only the requester can cancel this request.")
        return redirect(blood_request.get_absolute_url())
    if request.method == "POST":
        try:
            services.cancel_request(
                blood_request, request.user, request.POST.get("note", "")
            )
            messages.success(request, f"{blood_request.reference} cancelled.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    return redirect(blood_request.get_absolute_url())


@login_required
def respond(request, reference):
    blood_request = get_object_or_404(_base_queryset(), reference=reference)
    if request.method != "POST":
        return redirect(blood_request.get_absolute_url())
    form = ResponseForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please shorten your message.")
        return redirect(blood_request.get_absolute_url())
    try:
        services.respond_to_request(
            blood_request, request.user, form.cleaned_data.get("message", "")
        )
        messages.success(
            request,
            "Response sent. The recipient can now see your name and contact number.",
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return redirect(blood_request.get_absolute_url())


@login_required
def response_action(request, pk):
    response = get_object_or_404(
        DonorResponse.objects.select_related("request", "donor"), pk=pk
    )
    blood_request = response.request
    if request.method != "POST":
        return redirect(blood_request.get_absolute_url())
    action = request.POST.get("action", "")
    try:
        new_status = DonorResponse.Status(action)
    except ValueError:
        messages.error(request, "Unknown action.")
        return redirect(blood_request.get_absolute_url())
    try:
        services.set_response_status(response, new_status, request.user)
        messages.success(
            request,
            f"Response marked as {DonorResponse.Status(new_status).label.lower()}.",
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return redirect(blood_request.get_absolute_url())
