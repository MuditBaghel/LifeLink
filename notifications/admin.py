from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("user__username", "user__first_name", "title", "body")
    list_editable = ("is_read",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "matching_requests", "emergency_requests", "camp_updates")
    search_fields = ("user__username", "user__first_name")
