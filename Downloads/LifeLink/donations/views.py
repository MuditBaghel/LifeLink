from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from core.forms import BootstrapForm

from .models import Certificate, DonationRecord
from .services import certificate_filename, certificate_pdf


class CertificateLookupForm(BootstrapForm):
    reference = forms.CharField(
        label="Certificate reference",
        max_length=40,
        widget=forms.TextInput(
            attrs={"placeholder": "LL-2026-C1F3A9", "autofocus": True}
        ),
    )

    def clean_reference(self):
        value = self.cleaned_data["reference"].strip().upper()
        if not value:
            raise forms.ValidationError("Enter the reference printed on the certificate.")
        return value


@login_required
def certificate_download(request, reference):
    record = DonationRecord.objects.select_related("donor").filter(
        issued_certificate__reference=reference
    ).first()
    if record is None:
        raise Http404("Certificate not found.")
    issued = record.issued_certificate
    is_owner = record.donor_id == request.user.pk
    is_staff = request.user.is_platform_admin or request.user.is_staff
    if not (is_owner or is_staff):
        messages.error(request, "That certificate belongs to another donor.")
        return redirect("console:home")
    if not record.verified:
        raise Http404("Certificates are issued only for verified donations.")

    pdf_bytes = certificate_pdf(issued)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{certificate_filename(issued)}"'
    )
    return response


def certificate_verify_entry(request):
    """Public lookup page for a certificate reference."""
    reference = (request.GET.get("reference") or "").strip()
    if reference:
        return redirect(reverse("donations:certificate_verify", args=[reference]))
    return render(
        request, "donations/verify_entry.html", {"form": CertificateLookupForm()}
    )


def certificate_verify(request, reference):
    """Public check that a certificate reference is genuine."""
    certificate = Certificate.objects.select_related(
        "donation", "donation__donor"
    ).filter(reference__iexact=reference.strip()).first()
    donation = certificate.donation if certificate else None
    return render(
        request,
        "donations/verify.html",
        {
            "certificate": certificate,
            "donation": donation,
            "reference": reference,
            "valid": bool(certificate and donation and donation.verified),
            "form": CertificateLookupForm(initial={"reference": reference}),
        },
    )
