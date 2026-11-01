"""Registration, authentication and access control tests."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from blood.models import BloodRequest
from donations.models import Certificate, DonationRecord
from notifications.models import Notification

from .models import DonorProfile, RecipientProfile, User


class RegistrationTests(TestCase):
    def test_donor_registration_creates_profile(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Asha",
                "last_name": "Kumar",
                "username": "asha.donor",
                "email": "asha@example.com",
                "phone": "9876500111",
                "city": "Ludhiana",
                "role": "donor",
                "blood_group": "O+",
                "date_of_birth": "1996-05-04",
                "gender": "female",
                "weight_kg": 56,
                "password1": "LifeLink@2026",
                "password2": "LifeLink@2026",
                "terms": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="asha.donor")
        self.assertEqual(user.role, User.Role.DONOR)
        self.assertEqual(user.donor_profile.blood_group, "O+")
        self.assertTrue(user.check_password("LifeLink@2026"))

    def test_recipient_registration_skips_donor_fields(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Ravi",
                "last_name": "Menon",
                "username": "ravi.recipient",
                "email": "ravi@example.com",
                "phone": "9876500222",
                "city": "Delhi",
                "role": "recipient",
                "password1": "LifeLink@2026",
                "password2": "LifeLink@2026",
                "terms": "on",
            },
        )
        user = User.objects.get(username="ravi.recipient")
        self.assertTrue(hasattr(user, "recipientprofile"))
        self.assertIsNone(user.donor_profile)

    def test_under_age_donor_registration_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Young",
                "last_name": "Donor",
                "username": "young.donor",
                "email": "young@example.com",
                "phone": "9876500333",
                "city": "Ludhiana",
                "role": "donor",
                "blood_group": "A+",
                "date_of_birth": str(date.today().replace(year=date.today().year - 16)),
                "password1": "LifeLink@2026",
                "password2": "LifeLink@2026",
                "terms": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="asha.donor").exists())
        self.assertContains(response, "at least 18 years old")


class AccessControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.donor = User.objects.create_user(
            username="access_donor",
            password="LifeLink@2026",
            role=User.Role.DONOR,
            city="Ludhiana",
        )
        DonorProfile.objects.create(
            user=cls.donor, blood_group="A+", city="Ludhiana", weight_kg=60
        )
        cls.recipient = User.objects.create_user(
            username="access_recipient",
            password="LifeLink@2026",
            role=User.Role.RECIPIENT,
            city="Ludhiana",
        )
        RecipientProfile.objects.create(user=cls.recipient, city="Ludhiana")
        cls.admin = User.objects.create_user(
            username="access_admin",
            password="LifeLink@2026",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        cls.request = BloodRequest.objects.create(
            requester=cls.recipient,
            patient_name="Patient",
            blood_group="A+",
            units_required=1,
            hospital_name="DMC",
            hospital_address="Tagore Nagar",
            city="Ludhiana",
            required_by=date.today(),
            contact_phone="9876500444",
        )

    def test_login_redirects_to_role_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "access_donor", "password": "LifeLink@2026"},
        )
        self.assertRedirects(response, reverse("console:donor_dashboard"))

    def test_donor_cannot_open_admin_console(self):
        self.client.login(username="access_donor", password="LifeLink@2026")
        response = self.client.get(reverse("console:admin_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_donor_cannot_open_camp_checkin_desk(self):
        self.client.login(username="access_donor", password="LifeLink@2026")
        response = self.client.get(reverse("camps:checkin"))
        self.assertEqual(response.status_code, 302)

    def test_admin_can_open_admin_console(self):
        self.client.login(username="access_admin", password="LifeLink@2026")
        response = self.client.get(reverse("console:admin_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_request_contact_hidden_from_anonymous_visitor(self):
        response = self.client.get(self.request.get_absolute_url())
        self.assertNotContains(response, "9876500444")
        self.assertContains(response, "Hidden")

    def test_request_contact_visible_to_owner(self):
        self.client.login(username="access_recipient", password="LifeLink@2026")
        response = self.client.get(self.request.get_absolute_url())
        self.assertContains(response, "9876500444")

    def test_unavailable_donor_is_not_listed_publicly(self):
        DonorProfile.objects.filter(user=self.donor).update(is_available=False)
        response = self.client.get(reverse("accounts:donor_directory"))
        self.assertNotContains(response, "access_donor")

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)


class NotificationPreferenceTests(TestCase):
    def test_duplicate_dedupe_key_is_not_stored_twice(self):
        from notifications.services import notify

        user = User.objects.create_user(
            username="notify_user", password="LifeLink@2026", role=User.Role.DONOR
        )
        first = notify(user, Notification.Kind.REQUEST, "First", dedupe_key="same-key")
        second = notify(user, Notification.Kind.REQUEST, "Second", dedupe_key="same-key")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(user.notifications.count(), 1)

    def test_preference_suppresses_notification(self):
        from notifications.services import get_preferences, notify

        user = User.objects.create_user(
            username="pref_user", password="LifeLink@2026", role=User.Role.DONOR
        )
        prefs = get_preferences(user)
        prefs.matching_requests = False
        prefs.save(update_fields=["matching_requests"])
        result = notify(user, Notification.Kind.REQUEST, "Suppressed")
        self.assertIsNone(result)
        self.assertEqual(user.notifications.count(), 0)
