"""Compatibility, matching and request lifecycle tests."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import DonorProfile, RecipientProfile, User
from donations.models import DonationRecord

from . import services
from .matching import (
    find_matching_donors,
    donor_groups_for_recipient,
    is_compatible,
    recipients_for_donor,
)
from .models import BloodRequest, DonorResponse


def make_user(username, role, city="Ludhiana", **extra):
    return User.objects.create_user(
        username=username, password="LifeLink@2026", role=role, city=city, **extra
    )


def make_donor(username, group, city="Ludhiana", available=True, last_donation=None):
    user = make_user(username, User.Role.DONOR, city=city)
    profile = DonorProfile.objects.create(
        user=user,
        blood_group=group,
        city=city,
        is_available=available,
        date_of_birth=date(1995, 1, 1),
        weight_kg=62,
        last_donation_date=last_donation,
    )
    return user, profile


class CompatibilityTests(TestCase):
    def test_o_negative_can_give_to_every_group(self):
        for group in ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]:
            self.assertTrue(is_compatible("O-", group))

    def test_ab_positive_can_only_give_to_ab_positive(self):
        self.assertTrue(is_compatible("AB+", "AB+"))
        self.assertFalse(is_compatible("AB+", "A+"))
        self.assertFalse(is_compatible("AB+", "O-"))

    def test_a_positive_can_give_to_a_and_ab(self):
        self.assertEqual(recipients_for_donor("A+"), ["A+", "AB+"])

    def test_recipient_o_negative_accepts_only_o_negative(self):
        self.assertEqual(donor_groups_for_recipient("O-"), ["O-"])

    def test_recipient_ab_positive_accepts_all_groups(self):
        self.assertEqual(len(donor_groups_for_recipient("AB+")), 8)


class MatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.recipient = make_user("needer", User.Role.RECIPIENT)
        RecipientProfile.objects.create(user=cls.recipient, city="Ludhiana")
        cls.request = BloodRequest.objects.create(
            requester=cls.recipient,
            patient_name="Test Patient",
            blood_group="A+",
            units_required=2,
            hospital_name="DMC Hospital",
            hospital_address="Tagore Nagar",
            city="Ludhiana",
            required_by=date.today() + timedelta(days=2),
            contact_phone="9876500000",
            urgency=BloodRequest.Urgency.URGENT,
        )

    def test_matching_donor_appears_with_reasons(self):
        user, profile = make_donor("donor_a", "O-")
        matches = find_matching_donors(self.request)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].donor, profile)
        self.assertTrue(any("compatible" in reason for reason in matches[0].reasons))
        self.assertTrue(any("Ludhiana" in reason for reason in matches[0].reasons))

    def test_incompatible_donor_is_not_matched(self):
        make_donor("donor_b", "B+")
        self.assertEqual(find_matching_donors(self.request), [])

    def test_donor_inside_90_day_gap_is_excluded(self):
        make_donor("donor_c", "A+", last_donation=date.today() - timedelta(days=20))
        self.assertEqual(find_matching_donors(self.request), [])

    def test_unavailable_donor_is_excluded(self):
        make_donor("donor_d", "A+", available=False)
        self.assertEqual(find_matching_donors(self.request), [])

    def test_same_city_scores_higher_than_another_city(self):
        _, local = make_donor("donor_local", "A+", city="Ludhiana")
        _, remote = make_donor("donor_far", "A+", city="Delhi")
        matches = {match.donor.pk: match.score for match in find_matching_donors(self.request)}
        self.assertGreater(matches[local.pk], matches[remote.pk])


class LifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.recipient = make_user("requester", User.Role.RECIPIENT)
        RecipientProfile.objects.create(user=cls.recipient, city="Ludhiana")
        cls.donor, cls.donor_profile = make_donor("donor_one", "A+", city="Ludhiana")
        cls.request = BloodRequest.objects.create(
            requester=cls.recipient,
            patient_name="Test Patient",
            blood_group="A+",
            units_required=1,
            hospital_name="DMC Hospital",
            hospital_address="Tagore Nagar",
            city="Ludhiana",
            required_by=date.today() + timedelta(days=2),
            contact_phone="9876500001",
            urgency=BloodRequest.Urgency.EMERGENCY,
        )

    def test_publish_moves_status_and_notifies_donor(self):
        notified = services.publish_request(self.request)
        self.request.refresh_from_db()
        self.assertEqual(notified, 1)
        self.assertEqual(self.request.status, BloodRequest.Status.POTENTIAL)
        self.assertEqual(self.donor.notifications.count(), 1)
        self.assertIn("Emergency", self.donor.notifications.first().title)

    def test_request_cannot_move_backwards(self):
        services.progress_to(self.request, BloodRequest.Status.SEARCHING)
        with self.assertRaises(ValidationError):
            services.progress_to(self.request, BloodRequest.Status.CREATED)

    def test_cancelled_request_cannot_be_published(self):
        services.cancel_request(self.request, self.recipient)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, BloodRequest.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            services.progress_to(self.request, BloodRequest.Status.SEARCHING)

    def test_donor_cannot_respond_to_own_request(self):
        own_request = BloodRequest.objects.create(
            requester=self.donor,
            patient_name="Self",
            blood_group="A+",
            units_required=1,
            hospital_name="DMC",
            hospital_address="x",
            city="Ludhiana",
            required_by=date.today() + timedelta(days=1),
            contact_phone="9876500002",
        )
        with self.assertRaises(ValidationError):
            services.respond_to_request(own_request, self.donor)

    def test_incompatible_donor_cannot_respond(self):
        other, _ = make_donor("donor_b_group", "B+")
        with self.assertRaises(ValidationError):
            services.respond_to_request(self.request, other)

    def test_duplicate_response_is_rejected(self):
        services.respond_to_request(self.request, self.donor)
        with self.assertRaises(ValidationError):
            services.respond_to_request(self.request, self.donor)

    def test_full_response_flow_records_donation_and_fulfils(self):
        response = services.respond_to_request(self.request, self.donor)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, BloodRequest.Status.RESPONSES)

        services.set_response_status(response, DonorResponse.Status.CONFIRMED, self.recipient)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, BloodRequest.Status.COORDINATION)

        services.set_response_status(response, DonorResponse.Status.COMPLETED, self.recipient)
        self.request.refresh_from_db()
        self.assertEqual(self.request.units_fulfilled, 1)
        self.assertEqual(self.request.status, BloodRequest.Status.FULFILLED)
        record = DonationRecord.objects.get(request=self.request)
        self.assertFalse(record.verified)

    def test_requester_can_cancel_but_donor_cannot_change_status(self):
        response = services.respond_to_request(self.request, self.donor)
        with self.assertRaises(ValidationError):
            services.set_response_status(
                response, DonorResponse.Status.COMPLETED, self.donor
            )
