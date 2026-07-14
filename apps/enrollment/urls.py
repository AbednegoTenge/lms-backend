from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.enrollment.views import SchoolClassViewSet, StudentViewSet

router = SimpleRouter()
router.register(r'classes', SchoolClassViewSet, basename='classes')
router.register(r'students', StudentViewSet, basename='students')

urlpatterns = [
    path('', include(router.urls)),
]
