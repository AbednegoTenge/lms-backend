from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.academics.views import (
    AcademicYearViewSet,
    CourseOutlineViewSet,
    CourseViewSet,
    LevelViewSet,
    ProgramViewSet,
    TeacherCourseAssignmentViewSet,
    TermViewSet,
)

router = DefaultRouter()
router.register(r'academic-years', AcademicYearViewSet, basename='academic-year')
router.register(r'terms', TermViewSet, basename='term')
router.register(r'levels', LevelViewSet, basename='level')
router.register(r'programs', ProgramViewSet, basename='program')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'assignments', TeacherCourseAssignmentViewSet, basename='assignment')

# Nested: /api/v1/assignments/{assignment_pk}/outline/
outline_list = CourseOutlineViewSet.as_view({'get': 'retrieve', 'put': 'update'})

urlpatterns = [
    path('', include(router.urls)),
    path('assignments/<uuid:assignment_pk>/outline/', outline_list, name='assignment-outline'),
]
