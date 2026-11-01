from django.urls import path

from . import views

app_name = "console"

urlpatterns = [
    path("", views.home, name="home"),
    # Donor
    path("donor/", views.donor_dashboard, name="donor_dashboard"),
    path("availability/toggle/", views.toggle_availability, name="toggle_availability"),
    path("responses/", views.my_responses, name="my_responses"),
    path("donations/", views.my_donations, name="my_donations"),
    path("certificates/", views.certificates, name="certificates"),
    path("achievements/", views.achievements, name="achievements"),
    path("volunteering/", views.volunteering, name="volunteering"),
    # Recipient
    path("recipient/", views.recipient_dashboard, name="recipient_dashboard"),
    path("requests/", views.my_requests, name="my_requests"),
    # Administrator
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/users/", views.admin_users, name="admin_users"),
    path("admin/users/<int:pk>/", views.admin_user_detail, name="admin_user_detail"),
    path("admin/users/<int:pk>/<str:action>/", views.admin_user_action, name="admin_user_action"),
    path("admin/requests/", views.admin_requests, name="admin_requests"),
    path("admin/requests/<int:pk>/status/", views.admin_request_status, name="admin_request_status"),
    path("admin/donations/", views.admin_donations, name="admin_donations"),
    path("admin/donations/<int:pk>/<str:action>/", views.admin_donation_action,
         name="admin_donation_action"),
    path("admin/camps/", views.admin_camps, name="admin_camps"),
    path("admin/camps/new/", views.camp_create, name="camp_create"),
    path("admin/camps/<int:pk>/edit/", views.camp_edit, name="camp_edit"),
    path("admin/camps/<int:pk>/registrations/", views.camp_registrations,
         name="camp_registrations"),
    path("admin/registrations/<int:pk>/<str:action>/", views.registration_action,
         name="registration_action"),
    path("admin/volunteers/", views.admin_volunteers, name="admin_volunteers"),
    path("admin/volunteers/<int:pk>/<str:action>/", views.volunteer_action, name="volunteer_action"),
    path("admin/feedback/", views.admin_feedback, name="admin_feedback"),
    path("admin/feedback/messages/<int:pk>/read/", views.mark_message_read, name="mark_message_read"),
    path("admin/announcements/", views.announcements, name="announcements"),
    path("admin/analytics/", views.analytics, name="analytics"),
    path("admin/export/<str:dataset>/", views.export_csv, name="export_csv"),
]
