"""Account helpers shared by registration, profile editing and the seeder."""

from django.utils import timezone

from .models import DonorProfile, RecipientProfile, User, VolunteerProfile


def ensure_profiles(user):
    """Create the profile row that belongs to this user's role, if it is missing."""
    if user.role == User.Role.DONOR and not user.donor_profile:
        DonorProfile.objects.create(
            user=user,
            blood_group="O+",
            city=user.city or "Chandigarh",
        )
    if user.role == User.Role.RECIPIENT and not user.recipient_profile:
        RecipientProfile.objects.create(user=user, city=user.city or "Chandigarh")
    return user


def get_volunteer_profile(user):
    return getattr(user, "volunteerprofile", None)


def ensure_volunteer_profile(user, city="", phone="", motivation=""):
    profile, _ = VolunteerProfile.objects.get_or_create(
        user=user,
        defaults={"city": city or user.city or "Chandigarh", "phone": phone, "motivation": motivation},
    )
    return profile


def verify_donor(donor, admin_user):
    donor.is_verified = True
    donor.verified_at = timezone.now()
    donor.save(update_fields=["is_verified", "verified_at"])
    return donor


def public_donor_contact_allowed(donor):
    return bool(donor.share_contact and donor.user.phone)
