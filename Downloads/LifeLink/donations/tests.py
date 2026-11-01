"""Donation verification, certificate and achievement tests."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import DonorProfile, User

from . import services
from .models import Certificate, DonationRecord


def make_user(username, role=User.Role.DONOR, staff=False):
    user = User.objects.create_user(
        username=username, password="LifeLink@2026", role=role, city="Ludhiana"
    )
    if staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


class DonationVerificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        services.ensure_achievement_catalogue()
        cls.admin = make_user("verify_admin", role=User.Role.ADMIN, staff=True)
        cls.donor = make_user("cert_donor")
        cls.profile = DonorProfile.objects.create(
            user=cls.donor, blood_group="A+", city="Ludhiana", weight_kg=60
        )
        cls.record = services.record_donation(
            donor=cls.donor,
            donation_date=date.today() - timedelta(days=10),
            units=1,
            hospital="DMC Hospital",
        )

    def test_certificate_is_refused_for_unverified_donation(self):
        with self.assertRaises(ValidationError):
            services.issue_certificate(self.record)

    def test_verification_issues_certificate_and_achievement(self):
        certificate = services.verify_donation(self.record, self.admin)
        self.record.refresh_from_db()
        self.assertTrue(self.record.verified)
        self.assertEqual(certificate.donation, self.record)
        self.assertTrue(
            self.donor.achievements.filter(achievement__code="first-donation").exists()
        )

    def test_verified_donation_updates_last_donation_date(self):
        services.verify_donation(self.record, self.admin)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_donation_date, self.record.donation_date)

    def test_donation_cannot_be_verified_twice(self):
        services.verify_donation(self.record, self.admin)
        with self.assertRaises(ValidationError):
            services.verify_donation(self.record, self.admin)

    def test_repeated_record_for_same_camp_is_not_duplicated(self):
        from camps.models import DonationCamp

        camp = DonationCamp.objects.create(
            title="Donation Camp",
            organizer="LifeLink",
            venue="Hall",
            address="Sector 17",
            city="Chandigarh",
            starts_at=date.today(),
            ends_at=date.today(),
            capacity=10,
        )
        first = services.record_donation(donor=self.donor, camp=camp, hospital="Hall")
        second = services.record_donation(donor=self.donor, camp=camp, hospital="Hall")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(DonationRecord.objects.filter(camp=camp).count(), 1)

    def test_achievement_thresholds_award_once(self):
        services.verify_donation(self.record, self.admin)
        for offset in (40, 80):
            services.record_donation(
                donor=self.donor,
                donation_date=date.today() - timedelta(days=offset),
                units=1,
                hospital="Camp Hospital",
                verified=True,
                verified_by=self.admin,
            )
        services.award_achievements(self.donor)
        services.award_achievements(self.donor)
        codes = list(
            self.donor.achievements.values_list("achievement__code", flat=True)
        )
        self.assertEqual(codes.count("community-helper"), 1)


class CertificateAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        services.ensure_achievement_catalogue()
        cls.admin = make_user("pdf_admin", role=User.Role.ADMIN, staff=True)
        cls.donor = make_user("pdf_donor")
        DonorProfile.objects.create(
            user=cls.donor, blood_group="O+", city="Ludhiana", weight_kg=60
        )
        record = services.record_donation(
            donor=cls.donor,
            donation_date=date.today() - timedelta(days=30),
            units=1,
            hospital="Civil Hospital",
        )
        cls.certificate = services.verify_donation(record, cls.admin)

    def test_donor_can_download_own_certificate_pdf(self):
        self.client.login(username="pdf_donor", password="LifeLink@2026")
        response = self.client.get(
            reverse("donations:certificate_download", args=[self.certificate.reference])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_other_user_cannot_download_certificate(self):
        make_user("pdf_other")
        self.client.login(username="pdf_other", password="LifeLink@2026")
        response = self.client.get(
            reverse("donations:certificate_download", args=[self.certificate.reference])
        )
        self.assertEqual(response.status_code, 302)

    def test_public_verification_page_accepts_reference(self):
        response = self.client.get(
            reverse("donations:certificate_verify", args=[self.certificate.reference])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This certificate is genuine")

    def test_unknown_reference_reports_not_found(self):
        response = self.client.get(
            reverse("donations:certificate_verify", args=["LL-0000-NOPE"])
        )
        self.assertContains(response, "No verified certificate found")


class ExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("csv_admin", role=User.Role.ADMIN, staff=True)
        make_user("csv_donor")

    def test_staff_can_export_donations_csv(self):
        self.client.login(username="csv_admin", password="LifeLink@2026")
        response = self.client.get(reverse("console:export_csv", args=["donations"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_non_staff_cannot_export(self):
        self.client.login(username="csv_donor", password="LifeLink@2026")
        response = self.client.get(reverse("console:export_csv", args=["users"]))
        self.assertEqual(response.status_code, 302)
