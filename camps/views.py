"""Camp discovery, registration, QR tickets, staff check-in and feedback."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import admin_required
from accounts.models import CITIES
from accounts.services import ensure_volunteer_profile

from . import services
from .forms import CheckInForm, FeedbackForm, VolunteerApplyForm
from .models import CampFeedback, CampRegistration, DonationCamp, VolunteerAssignment


def camp_list(request):
    scope = request.GET.get("scope", "upcoming")
    query = request.GET.get("q", "").strip()
    city = request.GET.get("city", "").strip()

    queryset = DonationCamp.objects.select_related("created_by")
    if scope == "past":
        queryset = queryset.past()
    elif scope == "all":
        queryset = queryset.order_by("starts_at")
    else:
        queryset = queryset.upcoming()

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(venue__icontains=query)
            | Q(organizer__icontains=query)
            | Q(city__icontains=query)
        )
    if city:
        queryset = queryset.filter(city__iexact=city)

    queryset = queryset.annotate(registration_count=Count("registrations"))
    paginator = Paginator(queryset, 8)
    page = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)

    my_registrations = {}
    if request.user.is_authenticated:
        my_registrations = {
            registration.camp_id: registration
            for registration in CampRegistration.objects.filter(user=request.user)
        }
        for camp in page.object_list:
            camp.my_registration = my_registrations.get(camp.pk)

    return render(
        request,
        "camps/camp_list.html",
        {
            "page": page,
            "total": paginator.count,
            "cities": CITIES,
            "filters": {"q": query, "city": city, "scope": scope},
            "querystring": querystring.urlencode(),
            "my_registrations": my_registrations,
        },
    )


def camp_detail(request, pk):
    camp = get_object_or_404(
        DonationCamp.objects.annotate(registration_count=Count("registrations")), pk=pk
    )
    registration = None
    if request.user.is_authenticated:
        registration = camp.registrations.filter(user=request.user).first()

    feedback_form = FeedbackForm()
    volunteer_form = VolunteerApplyForm()
    assignment = None
    if request.user.is_authenticated:
        assignment = camp.volunteer_assignments.filter(volunteer=request.user).first()

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        form_name = request.POST.get("form_name")
        if form_name == "feedback":
            feedback_form = FeedbackForm(request.POST)
            if feedback_form.is_valid():
                try:
                    services.save_feedback(
                        camp,
                        request.user,
                        int(feedback_form.cleaned_data["rating"]),
                        feedback_form.cleaned_data.get("comment", ""),
                    )
                    messages.success(request, "Feedback saved. Thank you.")
                    return redirect(camp.get_absolute_url())
                except ValidationError as error:
                    messages.error(request, error.messages[0])
        elif form_name == "volunteer":
            volunteer_form = VolunteerApplyForm(request.POST)
            if volunteer_form.is_valid():
                ensure_volunteer_profile(request.user, city=camp.city)
                try:
                    services.apply_as_volunteer(
                        camp,
                        request.user,
                        volunteer_form.cleaned_data["duty"],
                        volunteer_form.cleaned_data.get("note", ""),
                    )
                    messages.success(
                        request,
                        "Volunteer request sent. An administrator confirms duties before the camp.",
                    )
                    return redirect(camp.get_absolute_url())
                except ValidationError as error:
                    messages.error(request, error.messages[0])

    return render(
        request,
        "camps/camp_detail.html",
        {
            "camp": camp,
            "registration": registration,
            "assignment": assignment,
            "feedback_form": feedback_form,
            "volunteer_form": volunteer_form,
            "feedback": camp.feedback_entries.select_related("user")[:6],
            "volunteers": camp.volunteer_assignments.select_related("volunteer"),
            "can_give_feedback": bool(
                registration
                and camp.is_past
                and not camp.feedback_entries.filter(user=request.user).exists()
            ),
        },
    )


@login_required
def camp_register(request, pk):
    camp = get_object_or_404(DonationCamp, pk=pk)
    if request.method == "POST":
        try:
            registration = services.register_for_camp(camp, request.user)
            messages.success(
                request, f"Registered for {camp.title}. Your QR ticket is ready."
            )
            return redirect(registration.ticket_url)
        except ValidationError as error:
            messages.error(request, error.messages[0])
    return redirect(camp.get_absolute_url())


@login_required
def camp_cancel(request, pk):
    camp = get_object_or_404(DonationCamp, pk=pk)
    registration = camp.registrations.filter(user=request.user).first()
    if request.method == "POST" and registration:
        try:
            services.cancel_registration(registration, request.user)
            messages.success(request, "Registration cancelled. The slot is free again.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    return redirect(camp.get_absolute_url())


def ticket(request, token):
    registration = get_object_or_404(
        CampRegistration.objects.select_related("camp", "user"), qr_token=token
    )
    is_owner = request.user.is_authenticated and request.user.pk == registration.user_id
    is_staff = request.user.is_authenticated and (
        request.user.is_platform_admin or request.user.is_staff
    )
    if not (is_owner or is_staff):
        messages.error(request, "This ticket belongs to another account.")
        return redirect("camps:camp_list")

    return render(
        request,
        "camps/ticket.html",
        {
            "registration": registration,
            "camp": registration.camp,
            "qr": services.ticket_qr(registration, request),
            "is_staff": is_staff,
        },
    )


@admin_required
def checkin(request):
    """Staff desk: enter a registration code or open a scanned QR link."""
    form = CheckInForm(request.POST or None)
    registration = None
    error = None
    if request.method == "POST":
        registration = services.find_registration_by_token(form.data.get("token"))
        if not registration:
            error = "No registration matches that code."
        else:
            try:
                registration, _donation = services.check_in(registration, request.user)
                messages.success(
                    request,
                    f"{registration.user.display_name} checked in for {registration.camp.title}.",
                )
                return redirect("camps:checkin")
            except ValidationError as validation_error:
                error = validation_error.messages[0]

    today = timezone.localdate()
    todays = (
        CampRegistration.objects.filter(camp__starts_at__date=today)
        .select_related("camp", "user")
        .order_by("status", "user__first_name")
    )
    return render(
        request,
        "camps/checkin.html",
        {
            "form": form,
            "error": error,
            "registration": registration,
            "todays_registrations": todays,
            "recent": CampRegistration.objects.select_related("camp", "user").order_by(
                "-registered_at"
            )[:8],
        },
    )


@admin_required
def checkin_scan(request, token):
    registration = services.find_registration_by_token(token)
    if not registration:
        messages.error(request, "That QR code does not match a registration.")
        return redirect("camps:checkin")
    if request.method == "POST":
        try:
            registration, _donation = services.check_in(registration, request.user)
            messages.success(
                request,
                f"{registration.user.display_name} checked in for {registration.camp.title}.",
            )
            return redirect("camps:ticket", token=registration.qr_token)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect("camps:ticket", token=registration.qr_token)
    return render(
        request,
        "camps/checkin_confirm.html",
        {"registration": registration, "camp": registration.camp},
    )
