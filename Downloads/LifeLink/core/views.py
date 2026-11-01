"""Public marketing pages plus the aggregated homepage statistics."""

from django.contrib import messages
from django.db.models import Case, Count, IntegerField, Q, Sum, When
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts.models import BLOOD_GROUPS, CITIES, DonorProfile, RecipientProfile
from blood.models import BloodRequest
from camps.models import DonationCamp
from donations.models import DonationRecord

from . import content
from .forms import ContactForm
from .models import ContactMessage


def _availability_board():
    """Available and immediately eligible donors per blood group."""
    from datetime import date, timedelta

    from django.conf import settings

    cutoff = date.today() - timedelta(days=settings.DONATION_INTERVAL_DAYS)
    rows = []
    donors = DonorProfile.objects.filter(is_available=True).only(
        "blood_group", "last_donation_date"
    )
    counts = {group: {"available": 0, "ready": 0} for group in BLOOD_GROUPS}
    for donor in donors:
        if donor.blood_group not in counts:
            continue
        counts[donor.blood_group]["available"] += 1
        if donor.last_donation_date is None or donor.last_donation_date <= cutoff:
            counts[donor.blood_group]["ready"] += 1
    peak = max([value["ready"] for value in counts.values()] or [0]) or 1
    for group in BLOOD_GROUPS:
        value = counts[group]
        rows.append(
            {
                "group": group,
                "available": value["available"],
                "ready": value["ready"],
                "percent": round(value["ready"] / peak * 100),
            }
        )
    return rows


def home(request):
    open_requests = BloodRequest.objects.open().with_related()
    urgency_order = Case(
        When(urgency=BloodRequest.Urgency.EMERGENCY, then=0),
        When(urgency=BloodRequest.Urgency.URGENT, then=1),
        default=2,
        output_field=IntegerField(),
    )
    verified = DonationRecord.objects.filter(verified=True)

    top_donors = (
        DonorProfile.objects.filter(is_verified=True)
        .select_related("user")
        .annotate(
            verified_count=Count(
                "user__donations", filter=Q(user__donations__verified=True)
            )
        )
        .order_by("-verified_count", "user__first_name")[:4]
    )

    context = {
        "availability": _availability_board(),
        "stats": {
            "donors": DonorProfile.objects.count(),
            "available_donors": DonorProfile.objects.filter(is_available=True).count(),
            "recipients": RecipientProfile.objects.count(),
            "active_requests": open_requests.count(),
            "emergency_requests": open_requests.filter(
                urgency=BloodRequest.Urgency.EMERGENCY
            ).count(),
            "fulfilled_requests": BloodRequest.objects.filter(
                status=BloodRequest.Status.FULFILLED
            ).count(),
            "verified_donations": verified.count(),
            "units_collected": verified.aggregate(total=Sum("units"))["total"] or 0,
            "upcoming_camps": DonationCamp.objects.upcoming().count(),
            "cities": DonorProfile.objects.values("city").distinct().count(),
        },
        "recent_requests": open_requests.annotate(urgency_rank=urgency_order).order_by(
            "urgency_rank", "-created_at"
        )[:5],
        "camps": DonationCamp.objects.upcoming()[:3],
        "top_donors": top_donors,
        "how_it_works": content.HOW_IT_WORKS,
        "why_lifelink": content.WHY_LIFELINK,
        "awareness": content.AWARENESS_FACTS,
        "faqs": content.FAQ_ITEMS,
        "contact_details": content.CONTACT_DETAILS,
        "disclaimer": content.MEDICAL_DISCLAIMER,
        "cities": CITIES,
    }
    return render(request, "core/home.html", context)


def about(request):
    verified = DonationRecord.objects.filter(verified=True)
    context = {
        "how_it_works": content.HOW_IT_WORKS,
        "why_lifelink": content.WHY_LIFELINK,
        "awareness": content.AWARENESS_FACTS,
        "disclaimer": content.MEDICAL_DISCLAIMER,
        "stats": {
            "donors": DonorProfile.objects.count(),
            "camps": DonationCamp.objects.count(),
            "verified_donations": verified.count(),
            "units": verified.aggregate(total=Sum("units"))["total"] or 0,
        },
    }
    return render(request, "core/about.html", context)


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            ContactMessage.objects.create(**form.cleaned_data)
            messages.success(
                request,
                "Message received. The LifeLink team replies to the email you shared.",
            )
            return redirect("core:contact")
    else:
        form = ContactForm()
    return render(
        request,
        "core/contact.html",
        {"form": form, "contact_details": content.CONTACT_DETAILS},
    )


def faq(request):
    return render(
        request,
        "core/faq.html",
        {
            "faqs": content.FAQ_ITEMS,
            "awareness": content.AWARENESS_FACTS,
            "disclaimer": content.MEDICAL_DISCLAIMER,
        },
    )


def demo_accounts(request):
    from django.conf import settings

    return render(
        request,
        "core/demo.html",
        {"demo_mode": settings.DEMO_MODE, "accounts": content.DEMO_ACCOUNTS},
    )


def health(request):
    return JsonResponse({"status": "ok", "service": "lifelink"})
