from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import DonorProfile, RecipientProfile, User, VolunteerProfile


@admin.register(User)
class LifeLinkUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "role", "city", "is_active", "is_demo")
    list_filter = ("role", "is_active", "is_demo", "city")
    fieldsets = UserAdmin.fieldsets + (
        ("LifeLink", {"fields": ("role", "phone", "city", "avatar", "is_demo")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("LifeLink", {"fields": ("role", "phone", "city", "email")}),
    )


@admin.register(DonorProfile)
class DonorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "blood_group", "city", "is_available", "is_verified",
                    "last_donation_date")
    list_filter = ("blood_group", "city", "is_available", "is_verified")
    search_fields = ("user__username", "user__first_name", "user__last_name", "city")
    list_editable = ("is_available",)


@admin.register(RecipientProfile)
class RecipientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "city", "is_verified")
    list_filter = ("kind", "city", "is_verified")
    search_fields = ("user__username", "user__first_name", "user__last_name", "organisation")


@admin.register(VolunteerProfile)
class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "is_active", "joined_at")
    list_filter = ("is_active", "city")
    search_fields = ("user__username", "user__first_name", "user__last_name")
