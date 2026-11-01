"""Donation recording, verification, certificates and achievements."""

from datetime import date
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify

from .models import Achievement, Certificate, DonationRecord, DonorAchievement


def record_donation(
    donor,
    donation_date=None,
    units=1,
    hospital="",
    camp=None,
    blood_request=None,
    notes="",
    verified=False,
    verified_by=None,
):
    """Create a donation record, skipping duplicates for the same camp/request."""
    donation_date = donation_date or date.today()
    queryset = DonationRecord.objects.filter(donor=donor, donation_date=donation_date)
    if camp is not None:
        existing = DonationRecord.objects.filter(donor=donor, camp=camp).first()
        if existing:
            return existing
    if blood_request is not None:
        existing = DonationRecord.objects.filter(
            donor=donor, request=blood_request
        ).first()
        if existing:
            return existing
    if camp is None and blood_request is None and queryset.exists():
        return queryset.first()

    record = DonationRecord.objects.create(
        donor=donor,
        donation_date=donation_date,
        units=units,
        hospital=hospital,
        camp=camp,
        request=blood_request,
        notes=notes,
        verified=verified,
        verified_by=verified_by,
        verified_at=timezone.now() if verified else None,
    )
    if verified:
        issue_certificate(record, verified_by)
    return record


def record_completed_response(response, actor=None):
    blood_request = response.request
    donor_profile = response.donor.donor_profile
    record = record_donation(
        donor=response.donor,
        donation_date=date.today(),
        units=1,
        hospital=blood_request.hospital_name,
        blood_request=blood_request,
        notes=f"Recorded from confirmed response on {blood_request.reference}",
    )
    if donor_profile and (not donor_profile.last_donation_date
                          or donor_profile.last_donation_date < record.donation_date):
        donor_profile.last_donation_date = record.donation_date
        donor_profile.save(update_fields=["last_donation_date"])
    return record


def donation_count(donor):
    return DonationRecord.objects.filter(donor=donor, verified=True).count()


def camps_attended(donor):
    from camps.models import CampRegistration

    return CampRegistration.objects.filter(
        user=donor,
        status__in=[CampRegistration.Status.ATTENDED, CampRegistration.Status.CHECKED_IN],
    ).count()


def volunteer_duties(donor):
    return donor.camp_assignments.filter(is_confirmed=True).count()


def _criteria_value(donor, criteria):
    if criteria == Achievement.Criteria.DONATION_COUNT:
        return donation_count(donor)
    if criteria == Achievement.Criteria.CAMP_ATTENDANCE:
        return camps_attended(donor)
    if criteria == Achievement.Criteria.VOLUNTEER_COUNT:
        return volunteer_duties(donor)
    return 0


def award_achievements(donor):
    """Grant every achievement whose threshold the donor has reached."""
    awarded = []
    for achievement in Achievement.objects.all():
        if DonorAchievement.objects.filter(donor=donor, achievement=achievement).exists():
            continue
        if _criteria_value(donor, achievement.criteria) >= achievement.threshold:
            DonorAchievement.objects.create(donor=donor, achievement=achievement)
            awarded.append(achievement)
            notify(
                donor,
                Notification.Kind.ACHIEVEMENT,
                f"Achievement unlocked: {achievement.name}",
                achievement.description,
                url="/dashboard/achievements/",
                dedupe_key=f"achv-{achievement.code}",
            )
    return awarded


def achievement_board(donor):
    """All achievements with progress, for the achievements page."""
    board = []
    for achievement in Achievement.objects.all():
        value = _criteria_value(donor, achievement.criteria)
        award = DonorAchievement.objects.filter(
            donor=donor, achievement=achievement
        ).first()
        board.append(
            {
                "achievement": achievement,
                "awarded": award,
                "value": value,
                "target": achievement.threshold,
                "percent": min(int(round(value / achievement.threshold * 100)), 100)
                if achievement.threshold
                else 100,
            }
        )
    return board


def issue_certificate(record, issued_by=None):
    if not record.verified:
        raise ValidationError("Certificates are issued only for verified donations.")
    if record.certificate:
        return record.certificate
    reference = f"LL-{record.donation_date.year}-{record.reference.split('-')[-1]}"
    return Certificate.objects.create(
        reference=reference, donation=record, issued_by=issued_by
    )


def verify_donation(record, admin_user):
    """Mark a donation verified, then issue the certificate and achievements."""
    if record.verified:
        raise ValidationError("This donation is already verified.")
    record.verified = True
    record.verified_by = admin_user
    record.verified_at = timezone.now()
    record.save(update_fields=["verified", "verified_by", "verified_at"])

    donor_profile = record.donor.donor_profile
    if donor_profile and (
        not donor_profile.last_donation_date
        or donor_profile.last_donation_date < record.donation_date
    ):
        donor_profile.last_donation_date = record.donation_date
        donor_profile.save(update_fields=["last_donation_date"])

    certificate = issue_certificate(record, admin_user)
    award_achievements(record.donor)
    notify(
        record.donor,
        Notification.Kind.CERTIFICATE,
        f"Donation verified · certificate {certificate.reference}",
        f"Your donation on {record.donation_date:%d %b %Y} is verified. Download the certificate.",
        url=certificate.download_url,
        dedupe_key=f"cert-{certificate.reference}",
    )
    return certificate


def reject_donation(record, admin_user, reason=""):
    if record.verified:
        raise ValidationError("Verified donations cannot be removed.")
    record.notes = (record.notes + f" | Rejected: {reason}").strip(" |")
    record.save(update_fields=["notes"])
    notify(
        record.donor,
        Notification.Kind.DONATION,
        "A donation record needs attention",
        reason or "Please contact the LifeLink desk about your last donation.",
        url="/dashboard/donations/",
        dedupe_key=f"donation-reject-{record.pk}",
    )
    return record


def certificate_pdf(certificate):
    """Render the certificate as PDF bytes with LifeLink branding."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    record = certificate.donation
    donor = record.donor
    buffer = BytesIO()
    page = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=page)
    width, height = page

    navy = HexColor("#14243A")
    red = HexColor("#D92332")
    paper = HexColor("#F7F8FA")
    muted = HexColor("#5B6B80")

    pdf.setFillColor(paper)
    pdf.rect(0, 0, width, height, stroke=0, fill=1)

    pdf.setFillColor(navy)
    pdf.rect(0, 0, width, 18 * mm, stroke=0, fill=1)
    pdf.setFillColor(red)
    pdf.rect(0, 18 * mm, width, 2.2 * mm, stroke=0, fill=1)

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(20 * mm, height - 30 * mm, "LifeLink")
    pdf.setFont("Helvetica", 9.5)
    pdf.setFillColor(muted)
    pdf.drawString(20 * mm, height - 36 * mm, "Blood Donation & Emergency Donor Coordination")

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawString(20 * mm, height - 62 * mm, "Certificate of Blood Donation")
    pdf.setStrokeColor(red)
    pdf.setLineWidth(1.4)
    pdf.line(20 * mm, height - 68 * mm, width - 20 * mm, height - 68 * mm)

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(20 * mm, height - 82 * mm, "This certificate confirms that")
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(20 * mm, height - 96 * mm, donor.display_name.upper())
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        20 * mm,
        height - 106 * mm,
        f"donated {record.units} unit(s) of blood on "
        f"{record.donation_date:%d %B %Y} at {record.hospital}.",
    )
    if record.request_id:
        pdf.drawString(20 * mm, height - 113 * mm,
                       f"Linked request: {record.request.reference} "
                       f"({record.request.blood_group})")

    detail_y = height - 136 * mm
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(20 * mm, detail_y, "CERTIFICATE REFERENCE")
    pdf.drawString(95 * mm, detail_y, "VERIFIED ON")
    pdf.drawString(150 * mm, detail_y, "BLOOD GROUP")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(20 * mm, detail_y - 7 * mm, certificate.reference)
    verified_on = record.verified_at or certificate.issued_at
    pdf.drawString(95 * mm, detail_y - 7 * mm, f"{verified_on:%d %B %Y}")
    group = donor.donor_profile.blood_group if donor.donor_profile else "n/a"
    pdf.drawString(150 * mm, detail_y - 7 * mm, group)

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        20 * mm,
        30 * mm,
        "Verified by a LifeLink administrator. Check authenticity at "
        f"/certificates/{certificate.reference}/verify/",
    )
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica-Oblique", 8.5)
    pdf.drawString(
        20 * mm,
        24 * mm,
        "Compatibility information on LifeLink is preliminary guidance and is not medical "
        "approval for transfusion.",
    )
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(20 * mm, 7 * mm, f"LifeLink · {certificate.reference}")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def certificate_filename(certificate):
    return f"lifelink-certificate-{certificate.reference}.pdf"


def ensure_achievement_catalogue():
    """Idempotent seed of the achievement definitions."""
    definitions = [
        ("first-donation", "First Donation", "Complete your first verified blood donation.",
         Achievement.Criteria.DONATION_COUNT, 1, "bi-droplet-fill", 1),
        ("community-helper", "Community Helper", "Three verified donations on record.",
         Achievement.Criteria.DONATION_COUNT, 3, "bi-people-fill", 2),
        ("regular-donor", "Regular Donor", "Five verified donations over time.",
         Achievement.Criteria.DONATION_COUNT, 5, "bi-calendar2-check", 3),
        ("lifelink-hero", "LifeLink Hero", "Ten verified donations, the platform's highest honour.",
         Achievement.Criteria.DONATION_COUNT, 10, "bi-award-fill", 4),
        ("camp-volunteer", "Camp Volunteer", "Confirmed for a duty at a LifeLink donation camp.",
         Achievement.Criteria.VOLUNTEER_COUNT, 1, "bi-person-badge", 5),
        ("camp-regular", "Camp Regular", "Attended three or more LifeLink donation camps.",
         Achievement.Criteria.CAMP_ATTENDANCE, 3, "bi-calendar2-heart", 6),
    ]
    for code, name, description, criteria, threshold, icon, order in definitions:
        Achievement.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "criteria": criteria,
                "threshold": threshold,
                "icon": icon,
                "sort_order": order,
            },
        )
