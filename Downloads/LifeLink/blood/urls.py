from django.urls import path

from . import views

app_name = "blood"

urlpatterns = [
    path("", views.request_list, name="request_list"),
    path("new/", views.request_create, name="request_create"),
    path("emergency/", views.sos_create, name="sos_create"),
    path("<str:reference>/", views.request_detail, name="request_detail"),
    path("<str:reference>/edit/", views.request_update, name="request_update"),
    path("<str:reference>/cancel/", views.request_cancel, name="request_cancel"),
    path("<str:reference>/respond/", views.respond, name="respond"),
    path("responses/<int:pk>/action/", views.response_action, name="response_action"),
]
