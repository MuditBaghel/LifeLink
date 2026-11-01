"""Preliminary red-cell compatibility and donor/request matching.

The tables below describe red blood cell compatibility only. They are
educational guidance, not medical approval for transfusion.
"""

from dataclasses import dataclass, field

from accounts.models import BLOOD_GROUPS, DonorProfile

# donor group -> patient groups that donor can help with red cells
DONOR_TO_RECIPIENTS = {
    "O-": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
    "O+": {"O+", "A+", "B+", "AB+"},
    "A-": {"A-", "A+", "AB-", "AB+"},
    "A+": {"A+", "AB+"},
    "B-": {"B-", "B+", "AB-", "AB+"},
    "B+": {"B+", "AB+"},
    "AB-": {"AB-", "AB+"},
    "AB+": {"AB+"},
}


def recipients_for_donor(donor_group):
    """Patient blood groups a donor can help."""
    return [group for group in BLOOD_GROUPS if group in DONOR_TO_RECIPIENTS.get(donor_group, set())]


def donor_groups_for_recipient(recipient_group):
    """Donor blood groups that are compatible with a patient group."""
    return [
        group
        for group in BLOOD_GROUPS
        if recipient_group in DONOR_TO_RECIPIENTS.get(group, set())
    ]


def is_compatible(donor_group, recipient_group):
    return recipient_group in DONOR_TO_RECIPIENTS.get(donor_group, set())


def compatibility_kind(donor_group, recipient_group):
    if not is_compatible(donor_group, recipient_group):
        return None
    return "exact" if donor_group == recipient_group else "compatible"


def compatibility_explanation(donor_group, recipient_group):
    if donor_group == recipient_group:
        return f"{donor_group} matches the requested group exactly."
    if is_compatible(donor_group, recipient_group):
        return (
            f"{donor_group} red cells are compatible with {recipient_group} patients."
        )
    return f"{donor_group} red cells are not compatible with {recipient_group} patients."


@dataclass
class DonorMatch:
    donor: DonorProfile
    score: int = 0
    reasons: list = field(default_factory=list)
    exact: bool = False


def _score_donor(donor, blood_request):
    """Score a candidate donor against a request. None means "not contactable"."""
    if not donor.is_eligible or not donor.is_available:
        return None
    if not donor.meets_age_criteria:
        return None

    score = 0
    reasons = []
    exact = donor.blood_group == blood_request.blood_group
    if exact:
        score += 40
        reasons.append(f"{donor.blood_group} matches the requested group exactly")
    else:
        score += 30
        reasons.append(
            f"{donor.blood_group} red cells are compatible with {blood_request.blood_group} patients"
        )

    if donor.city.lower() == (blood_request.city or "").lower():
        score += 25
        reasons.append(f"Based in {donor.city}, the city on this request")

    score += 15
    reasons.append("Marked available for contact")

    if donor.is_verified:
        score += 8
        reasons.append("Profile verified by LifeLink")

    verified_donations = donor.verified_donation_count
    if verified_donations:
        score += min(verified_donations * 2, 10)
        reasons.append(
            f"{verified_donations} verified donation{'s' if verified_donations > 1 else ''} on record"
        )
    else:
        score += 4
        reasons.append("No donation in the last 90 days, so eligible now")

    return score, reasons, exact


def find_matching_donors(blood_request, limit=12, include_unavailable=False):
    """Compatible, available and eligible donors for a request, best first."""
    groups = donor_groups_for_recipient(blood_request.blood_group)
    queryset = DonorProfile.objects.select_related("user").filter(blood_group__in=groups)
    if not include_unavailable:
        queryset = queryset.filter(is_available=True)
    matches = []
    for donor in queryset:
        result = _score_donor(donor, blood_request)
        if result is None:
            continue
        score, reasons, exact = result
        matches.append(DonorMatch(donor=donor, score=score, reasons=reasons, exact=exact))
    matches.sort(key=lambda match: (-match.score, match.donor.user.first_name or ""))
    return matches[:limit] if limit else matches


def donor_pool_summary(blood_request):
    """Counts used to explain how big the contactable pool is."""
    groups = donor_groups_for_recipient(blood_request.blood_group)
    compatible = DonorProfile.objects.filter(blood_group__in=groups)
    available = compatible.filter(is_available=True)
    return {
        "compatible": compatible.count(),
        "available": available.count(),
        "contactable": len(find_matching_donors(blood_request, limit=None)),
        "same_city": compatible.filter(city__iexact=blood_request.city).count(),
        "groups": groups,
    }


def find_matching_requests(donor, queryset=None, limit=8):
    """Open requests this donor could help with, with the reason for each match."""
    from .models import BloodRequest

    if queryset is None:
        queryset = BloodRequest.objects.open()
    groups = recipients_for_donor(donor.blood_group)
    requests = queryset.filter(blood_group__in=groups).with_related()
    results = []
    for blood_request in requests:
        reasons = []
        score = 40 if blood_request.blood_group == donor.blood_group else 30
        reasons.append(
            compatibility_explanation(donor.blood_group, blood_request.blood_group)
        )
        if blood_request.city.lower() == (donor.city or "").lower():
            score += 25
            reasons.append(f"Same city: {blood_request.city}")
        if blood_request.urgency == BloodRequest.Urgency.EMERGENCY:
            score += 20
            reasons.append("Emergency priority request")
        elif blood_request.urgency == BloodRequest.Urgency.URGENT:
            score += 10
            reasons.append("Urgent request")
        if blood_request.status in (
            BloodRequest.Status.CREATED,
            BloodRequest.Status.SEARCHING,
        ):
            score += 5
            reasons.append("No donor has responded yet")
        results.append({"request": blood_request, "score": score, "reasons": reasons})
    results.sort(key=lambda item: (-item["score"], item["request"].required_by))
    return results[:limit] if limit else results
