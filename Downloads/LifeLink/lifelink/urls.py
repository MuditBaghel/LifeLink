from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("requests/", include("blood.urls")),
    path("camps/", include("camps.urls")),
    path("donations/", include("donations.urls")),
    path("notifications/", include("notifications.urls")),
    path("dashboard/", include("console.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
