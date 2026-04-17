from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ImproperlyConfigured
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.academics.models import (
    AcademicYear,
    Course,
    CourseOutline,
    Level,
    Program,
    TeacherCourseAssignment,
    Term,
)
from apps.academics.serializers import (
    AcademicYearSerializer,
    CourseOutlineSerializer,
    CourseSerializer,
    LevelSerializer,
    ProgramSerializer,
    TeacherCourseAssignmentSerializer,
    TermSerializer,
)
from apps.users.permissions import IsAdminOrSuperAdmin


class TransitionThrottle(UserRateThrottle):
    scope = 'transition'

    def get_rate(self):
        try:
            return super().get_rate()
        except ImproperlyConfigured:
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


class AdminWriteAuthReadMixin:
    """GET/HEAD/OPTIONS allowed for any authenticated user; write ops require Admin/SuperAdmin."""

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAdminOrSuperAdmin()]


# ---------------------------------------------------------------------------
# AcademicYear
# ---------------------------------------------------------------------------

class AcademicYearViewSet(AdminWriteAuthReadMixin, viewsets.ModelViewSet):
    serializer_class = AcademicYearSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_current']
    ordering_fields = ['start_date', 'name']

    def get_queryset(self):
        return AcademicYear.objects.select_related('created_by').all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        self.perform_create(serializer)
        return _ok(serializer.data, 'Academic year created.', status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        self.perform_update(serializer)
        return _ok(serializer.data, 'Academic year updated.')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return _ok(self.get_serializer(instance).data)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response({'success': True, 'message': 'Academic year deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Term
# ---------------------------------------------------------------------------

class TermViewSet(AdminWriteAuthReadMixin, viewsets.ModelViewSet):
    serializer_class = TermSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['academic_year', 'term_number', 'is_current']
    ordering_fields = ['term_number']

    def get_queryset(self):
        return Term.objects.select_related('academic_year').all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(serializer.data, 'Term created.', status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        self.perform_update(serializer)
        return _ok(serializer.data, 'Term updated.')

    def retrieve(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_object()).data)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response({'success': True, 'message': 'Term deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=['post'],
        url_path='transition',
        permission_classes=[IsAdminOrSuperAdmin],
        throttle_classes=[TransitionThrottle],
    )
    def transition(self, request):
        from apps.academics.services import TermTransitionService, TransitionError
        try:
            result = TermTransitionService.transition()
        except TransitionError as exc:
            return _err(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return _ok(result, 'Term transitioned successfully.')


# ---------------------------------------------------------------------------
# Level (read-only; seeded by migration)
# ---------------------------------------------------------------------------

class LevelViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LevelSerializer
    permission_classes = [IsAuthenticated]
    queryset = Level.objects.all()

    def retrieve(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_object()).data)

    def list(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_queryset(), many=True).data)


# ---------------------------------------------------------------------------
# Program (read-only; seeded by migration)
# ---------------------------------------------------------------------------

class ProgramViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = [IsAuthenticated]
    queryset = Program.objects.all()

    def retrieve(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_object()).data)

    def list(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_queryset(), many=True).data)


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

PROGRAM_COURSES_CACHE_TIMEOUT = 3600  # 1 hour


class CourseViewSet(AdminWriteAuthReadMixin, viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['course_type', 'program', 'is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']

    def get_queryset(self):
        return Course.objects.select_related('program').all()

    def _invalidate_program_cache(self, program_id):
        if program_id:
            cache.delete(f'program:{program_id}:courses')

    def list(self, request, *args, **kwargs):
        program_id = request.query_params.get('program')
        course_type = request.query_params.get('course_type')
        search = request.query_params.get('search')

        # Cache only when filtering by a single program with no other filters
        if program_id and not course_type and not search:
            cache_key = f'program:{program_id}:courses'
            cached = cache.get(cache_key)
            if cached is not None:
                return _ok(cached)

        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})

        data = self.get_serializer(qs, many=True).data

        if program_id and not course_type and not search:
            cache.set(f'program:{program_id}:courses', data, PROGRAM_COURSES_CACHE_TIMEOUT)

        return _ok(data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        course = serializer.save()
        self._invalidate_program_cache(course.program_id)
        return _ok(serializer.data, 'Course created.', status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_program_id = instance.program_id
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        course = serializer.save()
        self._invalidate_program_cache(old_program_id)
        self._invalidate_program_cache(course.program_id)
        return _ok(serializer.data, 'Course updated.')

    def retrieve(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_object()).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._invalidate_program_cache(instance.program_id)
        instance.delete()
        return Response({'success': True, 'message': 'Course deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='assign-teacher',
            permission_classes=[IsAdminOrSuperAdmin])
    def assign_teacher(self, request, pk=None):
        course = self.get_object()
        serializer = TeacherCourseAssignmentSerializer(data={
            'teacher': request.data.get('teacher_id'),
            'course': str(course.pk),
            'term': request.data.get('term_id'),
            'level': request.data.get('level_id'),
        })
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        assignment = serializer.save(assigned_by=request.user)
        return _ok({'assignment_id': str(assignment.pk)}, 'Teacher assigned.', status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# TeacherCourseAssignment
# ---------------------------------------------------------------------------

class TeacherCourseAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = TeacherCourseAssignmentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['teacher', 'course', 'term', 'level', 'is_active']

    def get_queryset(self):
        return (
            TeacherCourseAssignment.objects
            .select_related('teacher', 'course', 'term__academic_year', 'level', 'assigned_by')
            .all()
        )

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAdminOrSuperAdmin()]

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        self.perform_create(serializer)
        return _ok(serializer.data, 'Assignment created.', status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return _ok(self.get_serializer(self.get_object()).data)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        self.perform_update(serializer)
        return _ok(serializer.data, 'Assignment updated.')

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response({'success': True, 'message': 'Assignment deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# CourseOutline
# ---------------------------------------------------------------------------

class CourseOutlineViewSet(viewsets.GenericViewSet):
    """
    Outline is accessed via its assignment:
      GET  /api/v1/assignments/{assignment_pk}/outline/
      PUT  /api/v1/assignments/{assignment_pk}/outline/
    """
    serializer_class = CourseOutlineSerializer

    def _get_outline_or_404(self, assignment_pk):
        from rest_framework.exceptions import NotFound
        try:
            return (
                CourseOutline.objects
                .select_related('assignment__teacher')
                .prefetch_related('weekly_topics')
                .get(assignment_id=assignment_pk)
            )
        except CourseOutline.DoesNotExist:
            raise NotFound('Outline not found.')

    def retrieve(self, request, assignment_pk=None):
        outline = self._get_outline_or_404(assignment_pk)
        user = request.user
        allowed = user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL'])
        is_teacher_owner = user.has_role('TEACHER') and outline.assignment.teacher == user
        is_student = user.has_role('STUDENT')
        if not (allowed or is_teacher_owner or is_student):
            return Response(
                {'success': False, 'message': 'Permission denied.', 'data': None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return _ok(self.get_serializer(outline).data)

    def update(self, request, assignment_pk=None):
        outline = self._get_outline_or_404(assignment_pk)
        user = request.user
        is_owner = user.has_role('TEACHER') and outline.assignment.teacher == user
        is_admin = user.has_any_role(['ADMIN', 'SUPER_ADMIN'])
        if not (is_owner or is_admin):
            return Response(
                {'success': False, 'message': 'Permission denied.', 'data': None},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(outline, data=request.data, partial=False)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(serializer.data, 'Outline updated.')
