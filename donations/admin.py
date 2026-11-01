from django.contrib import admin

from .models import Achievement, Certificate, DonationRecord, DonorAchievement


@admin.register(DonationRecord)
class DonationRecordAdmin(admin.ModelAdmin):
    list_display = ("reference", "donor", "donation_date", "units", "hospital", "verified")
    list_filter = ("verified", "donation_date", "camp")
    search_fields = ("reference", "donor__username", "donor__first_name", "hospital")
    date_hierarchy = "donation_date"
    list_editable = ("verified",)


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("reference", "donation", "issued_at")
    search_fields = ("reference", "donation__donor__username")
    readonly_fields = ("reference", "donation", "issued_at")


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "criteria", "threshold", "sort_order")
    list_filter = ("criteria",)
    search_fields = ("name", "code")


@admin.register(DonorAchievement)
class DonorAchievementAdmin(admin.ModelAdmin):
    list_display = ("donor", "achievement", "awarded_at")
    list_filter = ("achievement",)
    search_fields = ("donor__username", "donor__first_name", "achievement__name")
