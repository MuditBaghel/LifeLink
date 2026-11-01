from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile, name="profile"),
    path("password/", views.password_change, name="password_change"),
    path("donors/", views.donor_directory, name="donor_directory"),
    path("donors/<int:pk>/", views.donor_detail, name="donor_detail"),
]
