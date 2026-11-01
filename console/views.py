"""Dashboards for donors, recipients and administrators, plus analytics."""

import csv
from calendar import month_abbr
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import admin_required
from accounts.models import BLOOD_GROUPS, CITIES, DonorProfile, RecipientProfile, User, VolunteerProfile
from blood import services as request_services
from blood.matching import find_matching_requests
from blood.models import BloodRequest, DonorResponse, RequestStatusEvent
from camps import services as camp_services
from camps.forms import CampForm
from camps.models import CampFeedback, CampRegistration, DonationCamp, VolunteerAssignment
from core.models import ContactMessage
from donations import services as donation_services
from donations.models import Achievement, Certificate, DonationRecord, DonorAchievement
from notifications.models import Notification
from notifications.services import notify_many

from .forms import AnnouncementForm


# ---------------------------------------------------------------------------
# Routing and shared helpers
# ---------------------------------------------------------------------------
@login_required
def home(request):
    return redirect(request.user.dashboard_url)


def _wrong_role(request, message="That dashboard belongs to another role."):
    messages.info(request, message)
    return redirect(request.user.dashboard_url)


def _paged(request, queryset, per_page=12):
    paginator = Paginator(queryset, per_page)
    page = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)
    return page, paginator.count, querystring.urlencode()


# ---------------------------------------------------------------------------
# Donor
# ---------------------------------------------------------------------------
@login_required
def donor_dashboard(request):
    if request.user.is_platform_admin:
        return _wrong_role(request)
    if not request.user.donor_profile:
        return _wrong_role(request, "This dashboard is for donor accounts.")

    donor = request.user.donor_profile
    open_requests = BloodRequest.objects.open().exclude(requester=request.user)
    matches = find_matching_requests(donor, queryset=open_requests, limit=5)
    responses = request.user.donor_responses.select_related(
        "request", "request__requester"
    )[:5]
    registrations = (
        request.user.camp_registrations.select_related("camp")
        .filter(camp__ends_at__gte=timezone.now())
        .exclude(status=CampRegistration.Status.CANCELLED)
        .order_by("camp__starts_at")
    )
    donations = request.user.donations.select_related("camp")
    board = donation_services.achievement_board(request.user)
    awarded = [row for row in board if row["awarded"]]
    next_up = [row for row in board if not row["awarded"]][:3]

    context = {
        "donor": donor,
        "matches": matches,
        "responses": responses,
        "registrations": registrations[:2],
        "verified_donations": donations.filter(verified=True),
        "pending_donations": donations.filter(verified=False),
        "donation_count": donations.filter(verified=True).count(),
        "units": donations.filter(verified=True).aggregate(total=Sum("units"))["total"] or 0,
        "awarded": awarded,
        "next_achievements": next_up,
        "open_request_count": open_requests.count(),
        "emergency_count": open_requests.emergencies().count(),
        "next_eligible": donor.next_eligible_date,
    }
    return render(request, "console/donor_dashboard.html", context)


@login_required
def toggle_availability(request):
    if request.method == "POST" and request.user.donor_profile:
        donor = request.user.donor_profile
        donor.is_available = not donor.is_available
        donor.save(update_fields=["is_available"])
        messages.success(
            request,
            "You are marked available for donor contact."
            if donor.is_available
            else "Availability turned off. You will not appear in donor search or matches.",
        )
    return redirect(request.user.dashboard_url)


@login_required
def my_responses(request):
    queryset = request.user.donor_responses.select_related(
        "request", "request__requester"
    )
    status = request.GET.get("status", "")
    if status:
        queryset = queryset.filter(status=status)
    page, total, querystring = _paged(request, queryset, 10)
    return render(
        request,
        "console/my_responses.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "status": status,
            "statuses": DonorResponse.Status.choices,
        },
    )


@login_required
def my_donations(request):
    queryset = request.user.donations.select_related("camp", "request", "issued_certificate")
    verified = request.GET.get("verified", "")
    if verified == "1":
        queryset = queryset.filter(verified=True)
    elif verified == "0":
        queryset = queryset.filter(verified=False)
    page, total, querystring = _paged(request, queryset, 10)
    return render(
        request,
        "console/my_donations.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "verified": verified,
            "units_total": queryset.filter(verified=True).aggregate(total=Sum("units"))["total"] or 0,
        },
    )


@login_required
def certificates(request):
    items = Certificate.objects.filter(donation__donor=request.user).select_related(
        "donation", "donation__camp"
    )
    return render(request, "console/certificates.html", {"certificates": items})


@login_required
def achievements(request):
    board = donation_services.achievement_board(request.user)
    return render(
        request,
        "console/achievements.html",
        {
            "board": board,
            "awarded": [row for row in board if row["awarded"]],
            "in_progress": [row for row in board if not row["awarded"]],
        },
    )


@login_required
def volunteering(request):
    assignments = request.user.camp_assignments.select_related("camp").order_by(
        "camp__starts_at"
    )
    registrations = request.user.camp_registrations.select_related("camp").order_by(
        "-camp__starts_at"
    )
    return render(
        request,
        "console/volunteering.html",
        {
            "assignments": assignments,
            "registrations": registrations,
            "volunteer_profile": request.user.volunteer_profile,
        },
    )


# ---------------------------------------------------------------------------
# Recipient
# ---------------------------------------------------------------------------
@login_required
def recipient_dashboard(request):
    if request.user.is_platform_admin:
        return _wrong_role(request)
    if not request.user.recipient_profile and not request.user.donor_profile:
        return _wrong_role(request, "This dashboard is for recipient accounts.")

    my_requests = BloodRequest.objects.with_related().filter(requester=request.user)
    active = my_requests.open()
    pending_responses = DonorResponse.objects.select_related(
        "request", "donor", "donor__donorprofile"
    ).filter(
        request__requester=request.user,
        status__in=[DonorResponse.Status.INTERESTED, DonorResponse.Status.CONFIRMED],
    )[:6]
    counts = {
        "active": active.count(),
        "emergency": active.filter(urgency=BloodRequest.Urgency.EMERGENCY).count(),
        "fulfilled": my_requests.filter(status=BloodRequest.Status.FULFILLED).count(),
        "total": my_requests.count(),
    }
    return render(
        request,
        "console/recipient_dashboard.html",
        {
            "my_requests": active.order_by("required_by")[:5],
            "counts": counts,
            "pending_responses": pending_responses,
            "recent_requests": my_requests[:5],
            "profile": request.user.recipient_profile,
        },
    )


@login_required
def my_requests(request):
    queryset = BloodRequest.objects.with_related().filter(requester=request.user)
    status = request.GET.get("status", "")
    if status == "open":
        queryset = queryset.open()
    elif status:
        queryset = queryset.filter(status=status)
    page, total, querystring = _paged(request, queryset, 10)
    return render(
        request,
        "console/my_requests.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "status": status,
            "statuses": BloodRequest.Status.choices,
        },
    )


# ---------------------------------------------------------------------------
# Administrator console
# ---------------------------------------------------------------------------
@admin_required
def admin_dashboard(request):
    verified = DonationRecord.objects.filter(verified=True)
    today = timezone.localdate()
    context = {
        "kpi": {
            "donors": DonorProfile.objects.count(),
            "available_donors": DonorProfile.objects.filter(is_available=True).count(),
            "recipients": RecipientProfile.objects.count(),
            "active_requests": BloodRequest.objects.open().count(),
            "emergency_requests": BloodRequest.objects.emergencies().count(),
            "pending_verifications": DonationRecord.objects.filter(verified=False).count(),
            "verified_donations": verified.count(),
            "units": verified.aggregate(total=Sum("units"))["total"] or 0,
            "upcoming_camps": DonationCamp.objects.upcoming().count(),
            "camp_registrations": CampRegistration.objects.filter(
                status__in=CampRegistration.ACTIVE_STATUSES
            ).count(),
        },
        "emergency_queue": BloodRequest.objects.emergencies().with_related()[:5],
        "pending_donations": DonationRecord.objects.filter(verified=False)
        .select_related("donor", "camp")[:6],
        "recent_requests": BloodRequest.objects.with_related()[:6],
        "recent_users": User.objects.order_by("-date_joined")[:6],
        "activity": RequestStatusEvent.objects.select_related("request", "actor")[:8],
        "today": today,
        "disclaimer": True,
    }
    return render(request, "console/admin_dashboard.html", context)


@admin_required
def admin_users(request):
    queryset = User.objects.annotate(
        donation_total=Count("donations", filter=Q(donations__verified=True))
    )
    role = request.GET.get("role", "")
    query = request.GET.get("q", "").strip()
    verified = request.GET.get("verified", "")

    if role:
        queryset = queryset.filter(role=role)
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(city__icontains=query)
        )
    if verified == "1":
        queryset = queryset.filter(donorprofile__is_verified=True)
    elif verified == "0":
        queryset = queryset.filter(role=User.Role.DONOR).filter(
            Q(donorprofile__is_verified=False) | Q(donorprofile__isnull=True)
        )
    queryset = queryset.order_by("-date_joined")

    page, total, querystring = _paged(request, queryset, 12)
    return render(
        request,
        "console/admin_users.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "filters": {"role": role, "q": query, "verified": verified},
            "roles": User.Role.choices,
        },
    )


@admin_required
def admin_user_detail(request, pk):
    user = get_object_or_404(User.objects.select_related("donorprofile",
                                                         "recipientprofile"), pk=pk)
    return render(
        request,
        "console/admin_user_detail.html",
        {
            "subject": user,
            "donations": user.donations.select_related("camp", "request")[:10],
            "requests": user.blood_requests.all()[:10],
            "responses": user.donor_responses.select_related("request")[:10],
            "certificates": Certificate.objects.filter(donation__donor=user),
            "achievements": user.achievements.select_related("achievement"),
        },
    )


@admin_required
def admin_user_action(request, pk, action):
    user = get_object_or_404(User, pk=pk)
    if request.method != "POST":
        return redirect("console:admin_user_detail", pk=pk)

    if action == "verify-donor" and user.donor_profile:
        user.donor_profile.is_verified = True
        user.donor_profile.verified_at = timezone.now()
        user.donor_profile.save(update_fields=["is_verified", "verified_at"])
        messages.success(request, f"{user.display_name}'s donor profile verified.")
    elif action == "unverify-donor" and user.donor_profile:
        user.donor_profile.is_verified = False
        user.donor_profile.verified_at = None
        user.donor_profile.save(update_fields=["is_verified", "verified_at"])
        messages.info(request, f"{user.display_name}'s verification removed.")
    elif action == "verify-recipient" and user.recipient_profile:
        user.recipient_profile.is_verified = True
        user.recipient_profile.save(update_fields=["is_verified"])
        messages.success(request, f"{user.display_name}'s recipient profile verified.")
    elif action == "toggle-active":
        if user.pk == request.user.pk:
            messages.error(request, "You cannot disable your own account.")
        else:
            user.is_active = not user.is_active
            user.save(update_fields=["is_active"])
            messages.info(
                request,
                f"{user.display_name} is now {'active' if user.is_active else 'disabled'}.",
            )
    else:
        messages.error(request, "Unknown action.")
    return redirect("console:admin_user_detail", pk=pk)


@admin_required
def admin_requests(request):
    queryset = BloodRequest.objects.with_related().annotate(
        response_total=Count("responses")
    )
    status = request.GET.get("status", "")
    urgency = request.GET.get("urgency", "")
    query = request.GET.get("q", "").strip()

    if status == "open":
        queryset = queryset.open()
    elif status:
        queryset = queryset.filter(status=status)
    if urgency:
        queryset = queryset.filter(urgency=urgency)
    if query:
        queryset = queryset.filter(
            Q(reference__icontains=query)
            | Q(patient_name__icontains=query)
            | Q(hospital_name__icontains=query)
            | Q(city__icontains=query)
        )
    queryset = queryset.order_by("-created_at")
    page, total, querystring = _paged(request, queryset, 15)

    return render(
        request,
        "console/admin_requests.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "filters": {"status": status, "urgency": urgency, "q": query},
            "statuses": BloodRequest.Status.choices,
            "urgencies": BloodRequest.Urgency.choices,
        },
    )


@admin_required
def admin_request_status(request, pk):
    blood_request = get_object_or_404(BloodRequest, pk=pk)
    if request.method == "POST":
        new_status = request.POST.get("status", "")
        try:
            if new_status == BloodRequest.Status.CANCELLED:
                request_services.cancel_request(
                    blood_request, request.user, request.POST.get("note", "")
                )
            else:
                request_services.progress_to(
                    blood_request,
                    new_status,
                    request.user,
                    request.POST.get("note", ""),
                )
            messages.success(
                request,
                f"{blood_request.reference} moved to "
                f"{blood_request.get_status_display()}.",
            )
        except (ValidationError, ValueError) as error:
            message = error.messages[0] if isinstance(error, ValidationError) else str(error)
            messages.error(request, message)
    return redirect(request.META.get("HTTP_REFERER", "/dashboard/admin/requests/"))


@admin_required
def admin_donations(request):
    scope = request.GET.get("scope", "pending")
    queryset = DonationRecord.objects.select_related("donor", "camp", "request", "verified_by")
    if scope == "pending":
        queryset = queryset.filter(verified=False)
    elif scope == "verified":
        queryset = queryset.filter(verified=True)
    page, total, querystring = _paged(request, queryset, 15)
    return render(
        request,
        "console/admin_donations.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "scope": scope,
            "pending_count": DonationRecord.objects.filter(verified=False).count(),
            "verified_count": DonationRecord.objects.filter(verified=True).count(),
        },
    )


@admin_required
def admin_donation_action(request, pk, action):
    record = get_object_or_404(DonationRecord, pk=pk)
    if request.method == "POST":
        try:
            if action == "verify":
                certificate = donation_services.verify_donation(record, request.user)
                messages.success(
                    request,
                    f"Donation {record.reference} verified. Certificate {certificate.reference} issued.",
                )
            elif action == "reject":
                donation_services.reject_donation(
                    record, request.user, request.POST.get("reason", "")
                )
                messages.info(request, "Donation record returned to the donor for follow-up.")
            else:
                messages.error(request, "Unknown action.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    return redirect("console:admin_donations")


@admin_required
def admin_camps(request):
    camps = DonationCamp.objects.annotate(
        registration_total=Count("registrations")
    ).order_by("-starts_at")
    page, total, querystring = _paged(request, camps, 10)
    return render(
        request,
        "console/admin_camps.html",
        {"page": page, "total": total, "querystring": querystring},
    )


@admin_required
def camp_create(request):
    form = CampForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        camp = form.save(commit=False)
        camp.created_by = request.user
        camp.save()
        messages.success(request, f"{camp.title} created.")
        return redirect("console:admin_camps")
    return render(
        request,
        "console/camp_form.html",
        {"form": form, "heading": "Create a donation camp"},
    )


@admin_required
def camp_edit(request, pk):
    camp = get_object_or_404(DonationCamp, pk=pk)
    form = CampForm(request.POST or None, instance=camp)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Camp updated.")
        return redirect("console:camp_registrations", pk=camp.pk)
    return render(
        request,
        "console/camp_form.html",
        {"form": form, "camp": camp, "heading": f"Edit {camp.title}"},
    )


@admin_required
def camp_registrations(request, pk):
    camp = get_object_or_404(DonationCamp, pk=pk)
    status = request.GET.get("status", "")
    queryset = camp.registrations.select_related("user", "checked_in_by")
    if status:
        queryset = queryset.filter(status=status)
    queryset = queryset.order_by("status", "user__first_name")
    page, total, querystring = _paged(request, queryset, 20)
    return render(
        request,
        "console/camp_registrations.html",
        {
            "camp": camp,
            "page": page,
            "total": total,
            "querystring": querystring,
            "status": status,
            "statuses": CampRegistration.Status.choices,
            "volunteers": camp.volunteer_assignments.select_related("volunteer"),
        },
    )


@admin_required
def registration_action(request, pk, action):
    registration = get_object_or_404(
        CampRegistration.objects.select_related("camp", "user"), pk=pk
    )
    if request.method == "POST":
        try:
            if action == "checkin":
                camp_services.check_in(registration, request.user)
                messages.success(
                    request, f"{registration.user.display_name} checked in."
                )
            elif action == "attended":
                camp_services.mark_attended(registration, request.user)
                donation_services.award_achievements(registration.user)
                messages.success(request, "Marked as attended.")
            elif action == "no-show":
                camp_services.mark_no_show(registration)
                messages.info(request, "Marked as no show.")
            elif action == "cancel":
                camp_services.cancel_registration(registration, request.user)
                messages.info(request, "Registration cancelled.")
            else:
                messages.error(request, "Unknown action.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    return redirect(request.META.get("HTTP_REFERER",
                                     f"/dashboard/admin/camps/{registration.camp_id}/registrations/"))


@admin_required
def admin_volunteers(request):
    assignments = VolunteerAssignment.objects.select_related("camp", "volunteer")
    confirmed = request.GET.get("confirmed", "")
    if confirmed == "1":
        assignments = assignments.filter(is_confirmed=True)
    elif confirmed == "0":
        assignments = assignments.filter(is_confirmed=False)
    page, total, querystring = _paged(request, assignments.order_by("is_confirmed", "camp__starts_at"), 15)
    return render(
        request,
        "console/admin_volunteers.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "confirmed": confirmed,
            "volunteer_count": VolunteerProfile.objects.count(),
            "active_volunteers": VolunteerProfile.objects.filter(is_active=True).count(),
        },
    )


@admin_required
def volunteer_action(request, pk, action):
    assignment = get_object_or_404(VolunteerAssignment, pk=pk)
    if request.method == "POST":
        if action == "confirm":
            camp_services.confirm_assignment(assignment, request.user, True)
            messages.success(request, "Volunteer duty confirmed.")
        elif action == "unconfirm":
            camp_services.confirm_assignment(assignment, request.user, False)
            messages.info(request, "Volunteer confirmation removed.")
        elif action == "toggle-volunteer":
            volunteer = assignment.volunteer.volunteer_profile
            if volunteer:
                volunteer.is_active = not volunteer.is_active
                volunteer.save(update_fields=["is_active"])
                messages.info(request, "Volunteer availability updated.")
        else:
            messages.error(request, "Unknown action.")
    return redirect(request.META.get("HTTP_REFERER", "/dashboard/admin/volunteers/"))


@admin_required
def admin_feedback(request):
    feedback = CampFeedback.objects.select_related("camp", "user")
    messages_qs = ContactMessage.objects.all()
    page, total, querystring = _paged(request, feedback, 12)
    return render(
        request,
        "console/admin_feedback.html",
        {
            "page": page,
            "total": total,
            "querystring": querystring,
            "contact_messages": messages_qs[:10],
            "unread_messages": messages_qs.filter(is_read=False).count(),
            "average_rating": round(
                sum(item.rating for item in feedback) / feedback.count(), 1
            )
            if feedback.count()
            else None,
        },
    )


@admin_required
def mark_message_read(request, pk):
    contact = get_object_or_404(ContactMessage, pk=pk)
    if request.method == "POST":
        contact.is_read = True
        contact.save(update_fields=["is_read"])
    return redirect("console:admin_feedback")


@admin_required
def announcements(request):
    form = AnnouncementForm(request.POST or None)
    sent = 0
    if request.method == "POST" and form.is_valid():
        audience = form.cleaned_data["audience"]
        queryset = User.objects.filter(is_active=True)
        if audience == "donors":
            queryset = queryset.filter(role=User.Role.DONOR)
        elif audience == "recipients":
            queryset = queryset.filter(role=User.Role.RECIPIENT)
        elif audience == "volunteers":
            queryset = queryset.filter(volunteerprofile__isnull=False)
        elif audience == "city-donors":
            queryset = queryset.filter(
                role=User.Role.DONOR, donorprofile__city=form.cleaned_data["city"]
            )
        sent = notify_many(
            queryset,
            Notification.Kind.SYSTEM,
            form.cleaned_data["title"],
            form.cleaned_data["body"],
            url=form.cleaned_data.get("link", ""),
            dedupe_prefix="",
        )
        messages.success(request, f"Announcement delivered to {sent} account(s).")
        return redirect("console:announcements")
    recent = Notification.objects.filter(kind=Notification.Kind.SYSTEM).select_related("user")[:12]
    return render(
        request, "console/announcements.html", {"form": form, "recent": recent}
    )


@admin_required
def analytics(request):
    verified = DonationRecord.objects.filter(verified=True)
    today = timezone.localdate()

    months = []
    for offset in range(5, -1, -1):
        first = (today.replace(day=1) - timedelta(days=offset * 30)).replace(day=1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        count = verified.filter(
            donation_date__gte=first, donation_date__lt=next_month
        ).count()
        months.append({"label": month_abbr[first.month], "count": count})
    peak = max([item["count"] for item in months] or [0]) or 1
    for item in months:
        item["percent"] = round(item["count"] / peak * 100)

    group_rows = []
    donors_by_group = dict(
        DonorProfile.objects.values_list("blood_group").annotate(total=Count("id"))
    )
    donations_by_group = dict(
        verified.values_list("donor__donorprofile__blood_group").annotate(total=Count("id"))
    )
    group_peak = max(list(donors_by_group.values()) or [0]) or 1
    for group in BLOOD_GROUPS:
        group_rows.append(
            {
                "group": group,
                "donors": donors_by_group.get(group, 0),
                "donations": donations_by_group.get(group, 0),
                "percent": round(donors_by_group.get(group, 0) / group_peak * 100),
            }
        )

    status_rows = []
    total_requests = BloodRequest.objects.count()
    status_counts = dict(
        BloodRequest.objects.values_list("status").annotate(total=Count("id"))
    )
    for code, label in BloodRequest.Status.choices:
        count = status_counts.get(code, 0)
        if not count:
            continue
        status_rows.append(
            {
                "code": code,
                "label": label,
                "count": count,
                "percent": round(count / total_requests * 100) if total_requests else 0,
            }
        )
    status_rows.sort(key=lambda row: -row["count"])

    fulfilled = status_counts.get(BloodRequest.Status.FULFILLED, 0)
    camp_rows = [
        {
            "camp": camp,
            "registered": camp.registrations.filter(
                status__in=CampRegistration.ACTIVE_STATUSES
            ).count(),
            "attended": camp.registrations.filter(
                status__in=[CampRegistration.Status.CHECKED_IN,
                            CampRegistration.Status.ATTENDED]
            ).count(),
        }
        for camp in DonationCamp.objects.all()[:6]
    ]

    city_rows = (
        DonorProfile.objects.values("city")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )

    context = {
        "kpi": {
            "donors": DonorProfile.objects.count(),
            "recipients": RecipientProfile.objects.count(),
            "total_requests": total_requests,
            "open_requests": BloodRequest.objects.open().count(),
            "emergencies": BloodRequest.objects.emergencies().count(),
            "verified_donations": verified.count(),
            "units": verified.aggregate(total=Sum("units"))["total"] or 0,
            "fulfilment_rate": round(fulfilled / total_requests * 100) if total_requests else 0,
            "camp_registrations": CampRegistration.objects.filter(
                status__in=CampRegistration.ACTIVE_STATUSES
            ).count(),
            "volunteer_duties": VolunteerAssignment.objects.filter(is_confirmed=True).count(),
            "verified_volunteers": VolunteerProfile.objects.filter(is_active=True).count(),
            "city_count": DonorProfile.objects.values("city").distinct().count(),
        },
        "months": months,
        "group_rows": group_rows,
        "status_rows": status_rows,
        "camp_rows": camp_rows,
        "city_rows": city_rows,
        "has_data": bool(total_requests or verified.exists()),
        "average_rating": round(
            sum(item.rating for item in CampFeedback.objects.all())
            / CampFeedback.objects.count(),
            1,
        )
        if CampFeedback.objects.exists()
        else None,
    }
    return render(request, "console/analytics.html", context)


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------
def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


@admin_required
def export_csv(request, dataset):
    stamp = timezone.localdate().isoformat()

    if dataset == "donations":
        rows = [
            [
                record.reference,
                record.donor.display_name,
                record.donor.username,
                record.donation_date,
                record.units,
                record.hospital,
                "verified" if record.verified else "pending",
                record.camp.title if record.camp else "",
            ]
            for record in DonationRecord.objects.select_related("donor", "camp")
        ]
        return _csv_response(
            f"lifelink-donations-{stamp}.csv",
            ["Reference", "Donor", "Username", "Date", "Units", "Hospital", "State", "Camp"],
            rows,
        )

    if dataset == "requests":
        rows = [
            [
                item.reference,
                item.patient_name,
                item.blood_group,
                item.units_required,
                item.units_fulfilled,
                item.hospital_name,
                item.city,
                item.urgency,
                item.status,
                item.required_by,
                item.created_at.date(),
            ]
            for item in BloodRequest.objects.with_related()
        ]
        return _csv_response(
            f"lifelink-requests-{stamp}.csv",
            ["Reference", "Patient", "Blood group", "Units required", "Units filled",
             "Hospital", "City", "Priority", "Status", "Needed by", "Created"],
            rows,
        )

    if dataset == "users":
        rows = [
            [
                user.username,
                user.display_name,
                user.email,
                user.role,
                user.city,
                user.phone,
                "yes" if user.is_active else "no",
                user.date_joined.date(),
            ]
            for user in User.objects.all()
        ]
        return _csv_response(
            f"lifelink-users-{stamp}.csv",
            ["Username", "Name", "Email", "Role", "City", "Phone", "Active", "Joined"],
            rows,
        )

    if dataset == "camps":
        rows = [
            [
                camp.title,
                camp.organizer,
                camp.city,
                camp.venue,
                camp.starts_at,
                camp.capacity,
                camp.slots_taken,
                camp.status,
            ]
            for camp in DonationCamp.objects.all()
        ]
        return _csv_response(
            f"lifelink-camps-{stamp}.csv",
            ["Camp", "Organizer", "City", "Venue", "Starts", "Capacity", "Registered", "Status"],
            rows,
        )

    if dataset == "registrations":
        rows = [
            [
                registration.camp.title,
                registration.user.display_name,
                registration.status,
                registration.registered_at,
                registration.checked_in_at or "",
            ]
            for registration in CampRegistration.objects.select_related("camp", "user")
        ]
        return _csv_response(
            f"lifelink-camp-registrations-{stamp}.csv",
            ["Camp", "Person", "Status", "Registered at", "Checked in at"],
            rows,
        )

    messages.error(request, "Unknown export.")
    return redirect("console:admin_dashboard")
