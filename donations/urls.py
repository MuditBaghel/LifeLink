from django.urls import path

from . import views

app_name = "donations"

urlpatterns = [
    path("verify/", views.certificate_verify_entry, name="certificate_verify_entry"),
    path("verify/<str:reference>/", views.certificate_verify, name="certificate_verify"),
    path("<str:reference>/pdf/", views.certificate_download, name="certificate_download"),
]
