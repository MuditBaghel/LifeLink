from django.contrib import admin

from .models import BloodRequest, DonorResponse, RequestStatusEvent


class RequestStatusEventInline(admin.TabularInline):
    model = RequestStatusEvent
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "blood_group", "patient_name", "city", "urgency",
                    "status", "required_by", "units_required", "units_fulfilled")
    list_filter = ("urgency", "status", "city", "required_by")
    search_fields = ("reference", "patient_name", "hospital_name", "city")
    date_hierarchy = "created_at"
    readonly_fields = ("reference",)
    inlines = [RequestStatusEventInline]


@admin.register(DonorResponse)
class DonorResponseAdmin(admin.ModelAdmin):
    list_display = ("donor", "request", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("donor__username", "donor__first_name", "request__reference")


@admin.register(RequestStatusEvent)
class RequestStatusEventAdmin(admin.ModelAdmin):
    list_display = ("request", "status", "actor", "created_at")
    list_filter = ("status",)
    search_fields = ("request__reference", "note")
