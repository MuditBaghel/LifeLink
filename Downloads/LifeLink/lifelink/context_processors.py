"""Shared template context: navigation counts that every page needs."""

from django.db.models import Count, Q


def lifelink_context(request):
    from blood.models import BloodRequest
    from camps.models import DonationCamp

    user = getattr(request, "user", None)
    unread = 0
    if user is not None and user.is_authenticated:
        unread = user.notifications.filter(is_read=False).count()

    open_requests = BloodRequest.objects.filter(
        status__in=BloodRequest.OPEN_STATUSES
    ).exclude(urgency=BloodRequest.Urgency.EMERGENCY)

    emergency_count = BloodRequest.objects.filter(
        status__in=BloodRequest.OPEN_STATUSES,
        urgency=BloodRequest.Urgency.EMERGENCY,
    ).count()

    return {
        "nav_unread_count": unread,
        "nav_open_request_count": open_requests.count(),
        "nav_emergency_count": emergency_count,
        "nav_upcoming_camp_count": DonationCamp.objects.upcoming().count(),
    }
