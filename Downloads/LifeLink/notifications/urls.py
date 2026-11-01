from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("preferences/", views.preferences, name="preferences"),
    path("read/<int:pk>/", views.mark_read, name="mark_read"),
    path("open/<int:pk>/", views.open_notification, name="open"),
    path("read-all/", views.mark_all_read, name="mark_all_read"),
]
