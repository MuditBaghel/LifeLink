"""Authentication, donor discovery and profile management."""

from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    AccountForm,
    DonorProfileForm,
    LoginForm,
    RecipientProfileForm,
    RegistrationForm,
    VolunteerProfileForm,
)
from .models import BLOOD_GROUPS, CITIES, DonorProfile, User


def register(request):
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url)
    prefill = request.GET.get("role", "")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(
                request,
                "Account created. Add the remaining profile details so matching works well.",
            )
            return redirect("accounts:profile")
    else:
        init = {}
        if prefill == User.Role.RECIPIENT:
            init["role"] = User.Role.RECIPIENT
        elif prefill == User.Role.DONOR:
            init["role"] = User.Role.DONOR
        form = RegistrationForm(initial=init)
    return render(request, "accounts/register.html", {"form": form, "prefill_role": prefill})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url)
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, f"Signed in as {form.get_user().display_name}.")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect(form.get_user().dashboard_url)
        messages.error(request, "We could not sign you in with those details.")
    else:
        form = LoginForm(request)
    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def logout_view(request):
    if request.method != "POST":
        return redirect("core:home")
    logout(request)
    messages.info(request, "Signed out.")
    return redirect("core:home")


@login_required
def profile(request):
    user = request.user
    account_form = AccountForm(instance=request.user)
    donor_form = DonorProfileForm(instance=user.donor_profile) if user.donor_profile else None
    recipient_form = (
        RecipientProfileForm(instance=user.recipient_profile) if user.recipient_profile else None
    )
    volunteer_form = VolunteerProfileForm(
        instance=user.volunteer_profile,
        initial={} if user.volunteer_profile else {"city": user.city},
    )

    if request.method == "POST":
        form_name = request.POST.get("form_name", "account")
        if form_name == "account":
            account_form = AccountForm(request.POST, request.FILES, instance=user)
            if account_form.is_valid():
                account_form.save()
                messages.success(request, "Account details saved.")
                return redirect("accounts:profile")
        elif form_name == "donor" and donor_form:
            donor_form = DonorProfileForm(request.POST, instance=user.donor_profile)
            if donor_form.is_valid():
                profile_obj = donor_form.save(commit=False)
                profile_obj.user = user
                profile_obj.save()
                user.city = profile_obj.city
                user.save(update_fields=["city"])
                messages.success(request, "Donor profile updated.")
                return redirect("accounts:profile")
        elif form_name == "recipient" and recipient_form:
            recipient_form = RecipientProfileForm(request.POST, instance=user.recipient_profile)
            if recipient_form.is_valid():
                recipient_form.save()
                messages.success(request, "Recipient profile updated.")
                return redirect("accounts:profile")
        elif form_name == "volunteer":
            instance = user.volunteer_profile
            volunteer_form = VolunteerProfileForm(
                request.POST, instance=instance, initial={"city": user.city} if not instance else None
            )
            if volunteer_form.is_valid():
                volunteer_profile = volunteer_form.save(commit=False)
                volunteer_profile.user = user
                volunteer_profile.save()
                messages.success(request, "Volunteer profile saved.")
                return redirect("accounts:profile")
        messages.error(request, "Please correct the highlighted fields.")

    context = {
        "account_form": account_form,
        "donor_form": donor_form,
        "recipient_form": recipient_form,
        "volunteer_form": volunteer_form,
        "is_volunteer": bool(user.volunteer_profile),
    }
    return render(request, "accounts/profile.html", context)


@login_required
def password_change(request):
    form = PasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password changed.")
        return redirect("accounts:profile")
    return render(request, "accounts/password_change.html", {"form": form})


def donor_directory(request):
    cutoff = date.today() - timedelta(days=settings.DONATION_INTERVAL_DAYS)
    queryset = (
        DonorProfile.objects.filter(is_available=True)
        .select_related("user")
        .annotate(
            donation_count=Count("user__donations", filter=Q(user__donations__verified=True))
        )
    )

    query = request.GET.get("q", "").strip()
    group = request.GET.get("group", "").strip()
    city = request.GET.get("city", "").strip()
    eligible_only = request.GET.get("eligible") == "1"
    verified_only = request.GET.get("verified") == "1"
    sort = request.GET.get("sort", "donations")

    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(city__icontains=query)
            | Q(area__icontains=query)
        )
    if group in BLOOD_GROUPS:
        queryset = queryset.filter(blood_group=group)
    if city:
        queryset = queryset.filter(city__iexact=city)
    if eligible_only:
        queryset = queryset.filter(
            Q(last_donation_date__isnull=True) | Q(last_donation_date__lte=cutoff)
        )
    if verified_only:
        queryset = queryset.filter(is_verified=True)

    if sort == "donations":
        queryset = queryset.order_by("-is_verified", "-donation_count", "user__first_name")
    elif sort == "recent":
        queryset = queryset.order_by("-user__date_joined")
    else:
        queryset = queryset.order_by("city", "user__first_name")

    paginator = Paginator(queryset, 9)
    page = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(
        request,
        "accounts/donor_directory.html",
        {
            "page": page,
            "total": paginator.count,
            "groups": BLOOD_GROUPS,
            "cities": CITIES,
            "filters": {
                "q": query,
                "group": group,
                "city": city,
                "eligible": eligible_only,
                "verified": verified_only,
                "sort": sort,
            },
            "querystring": querystring.urlencode(),
        },
    )


def donor_detail(request, pk):
    donor = get_object_or_404(
        DonorProfile.objects.select_related("user"), pk=pk
    )
    from blood.matching import recipients_for_donor

    own_card = request.user.is_authenticated and request.user.pk == donor.user_id
    context = {
        "donor": donor,
        "own_card": own_card,
        "compatible_groups": recipients_for_donor(donor.blood_group),
        "achievements": donor.user.achievements.select_related("achievement"),
        "contact_visible": bool(own_card or (donor.share_contact and donor.user.phone)),
        "recent_donations": donor.user.donations.filter(verified=True)[:4],
    }
    return render(request, "accounts/donor_detail.html", context)
