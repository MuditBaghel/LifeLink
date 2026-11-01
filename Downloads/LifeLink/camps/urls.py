from django.urls import path

from . import views

app_name = "camps"

urlpatterns = [
    path("", views.camp_list, name="camp_list"),
    path("checkin/", views.checkin, name="checkin"),
    path("scan/<uuid:token>/", views.checkin_scan, name="checkin_scan"),
    path("tickets/<uuid:token>/", views.ticket, name="ticket"),
    path("<int:pk>/", views.camp_detail, name="camp_detail"),
    path("<int:pk>/register/", views.camp_register, name="camp_register"),
    path("<int:pk>/cancel/", views.camp_cancel, name="camp_cancel"),
]
