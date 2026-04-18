from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/', include('apps.academics.urls')),
    path('api/v1/', include('apps.enrollment.urls')),
    path('api/v1/', include('apps.assessments.urls')),
    path('api/v1/', include('apps.fees.urls')),
    path('api/v1/', include('apps.schedules.urls')),
    path('api/v1/', include('apps.announcements.urls')),
    path('api/v1/', include('apps.reports.urls')),
    path('api/v1/', include('apps.it_support.urls')),
]
