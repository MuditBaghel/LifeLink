from django.contrib import admin

from .models import CampFeedback, CampRegistration, DonationCamp, VolunteerAssignment


class CampRegistrationInline(admin.TabularInline):
    model = CampRegistration
    extra = 0
    fields = ("user", "status", "registered_at", "checked_in_at")
    readonly_fields = ("registered_at",)


@admin.register(DonationCamp)
class DonationCampAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "venue", "starts_at", "capacity", "status")
    list_filter = ("status", "city")
    search_fields = ("title", "venue", "organizer", "city")
    date_hierarchy = "starts_at"
    inlines = [CampRegistrationInline]


@admin.register(CampRegistration)
class CampRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "camp", "status", "registered_at", "checked_in_at")
    list_filter = ("status", "camp")
    search_fields = ("user__username", "user__first_name", "camp__title")
    readonly_fields = ("qr_token",)


@admin.register(VolunteerAssignment)
class VolunteerAssignmentAdmin(admin.ModelAdmin):
    list_display = ("volunteer", "camp", "duty", "is_confirmed")
    list_filter = ("is_confirmed", "duty", "camp")
    search_fields = ("volunteer__username", "volunteer__first_name", "camp__title")


@admin.register(CampFeedback)
class CampFeedbackAdmin(admin.ModelAdmin):
    list_display = ("camp", "user", "rating", "created_at")
    list_filter = ("rating", "camp")
    search_fields = ("user__username", "camp__title", "comment")
