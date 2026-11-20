from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", include("apps.panel.urls")),
    path("api/v1/", include("config.api_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.analysis.urls")),
    path("", include("apps.dashboard.urls")),
]
