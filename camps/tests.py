"""Camp capacity, QR tickets and staff check-in tests."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import DonorProfile, User
from donations.models import DonationRecord

from . import services
from .models import CampRegistration, DonationCamp


def make_user(username, role=User.Role.DONOR, staff=False):
    user = User.objects.create_user(
        username=username,
        password="LifeLink@2026",
        role=role,
        city="Ludhiana",
        phone="9876500000",
    )
    if staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


class CampTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("camp_admin", role=User.Role.ADMIN, staff=True)
        cls.donor = make_user("camp_donor")
        DonorProfile.objects.create(
            user=cls.donor, blood_group="O+", city="Ludhiana", weight_kg=60
        )
        start = timezone.now() + timedelta(days=5)
        cls.camp = DonationCamp.objects.create(
            title="Test Camp",
            organizer="LifeLink",
            venue="Community Hall",
            address="Sector 17",
            city="Chandigarh",
            starts_at=start,
            ends_at=start + timedelta(hours=5),
            capacity=2,
            contact_phone="0172 400 1120",
        )

    def test_registration_creates_active_record_and_ticket(self):
        registration = services.register_for_camp(self.camp, self.donor)
        self.assertTrue(registration.is_active)
        self.assertTrue(services.ticket_qr(registration).startswith("data:image/png;base64,"))

    def test_duplicate_registration_is_rejected(self):
        services.register_for_camp(self.camp, self.donor)
        with self.assertRaises(ValidationError):
            services.register_for_camp(self.camp, self.donor)

    def test_capacity_is_enforced(self):
        second = make_user("camp_donor_two")
        third = make_user("camp_donor_three")
        services.register_for_camp(self.camp, self.donor)
        services.register_for_camp(self.camp, second)
        self.camp.refresh_from_db()
        self.assertTrue(self.camp.is_full)
        self.assertEqual(self.camp.slots_available, 0)
        with self.assertRaises(ValidationError):
            services.register_for_camp(self.camp, third)

    def test_cancelling_releases_the_slot(self):
        registration = services.register_for_camp(self.camp, self.donor)
        services.cancel_registration(registration, self.donor)
        registration.refresh_from_db()
        self.assertEqual(registration.status, CampRegistration.Status.CANCELLED)
        self.camp.refresh_from_db()
        self.assertEqual(self.camp.slots_taken, 0)

    def test_only_staff_can_check_in(self):
        registration = services.register_for_camp(self.camp, self.donor)
        with self.assertRaises(ValidationError):
            services.check_in(registration, self.donor)

    def test_check_in_records_pending_donation_and_blocks_second_scan(self):
        registration = services.register_for_camp(self.camp, self.donor)
        services.check_in(registration, self.admin)
        registration.refresh_from_db()
        self.assertEqual(registration.status, CampRegistration.Status.CHECKED_IN)
        self.assertIsNotNone(registration.checked_in_at)
        donation = DonationRecord.objects.get(donor=self.donor, camp=self.camp)
        self.assertFalse(donation.verified)
        with self.assertRaises(ValidationError):
            services.check_in(registration, self.admin)

    def test_token_lookup_accepts_short_ticket_code(self):
        registration = services.register_for_camp(self.camp, self.donor)
        found = services.find_registration_by_token(registration.ticket_code)
        self.assertEqual(found, registration)

    def test_registration_closed_after_deadline(self):
        self.camp.registration_deadline = timezone.now() - timedelta(hours=1)
        self.camp.save(update_fields=["registration_deadline"])
        with self.assertRaises(ValidationError):
            services.register_for_camp(self.camp, self.donor)
