import datetime

from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.academics.models import Program, Term
from apps.enrollment.models import Enrollment, StudentProfile
from apps.enrollment.serializers import EnrollmentSerializer, StudentProfileSerializer
from apps.enrollment.services import EnrollmentService
from apps.users.models import CustomUser, Role, UserRole
from apps.users.permissions import (
    CanViewStudentCourses,
    IsAdminOrPrincipal,
    IsAdminOrPrincipalOrSelf,
    IsAdminOrSuperAdmin,
)
from apps.users.services import UserService


# ---------------------------------------------------------------------------
# Helpers (same pattern as academics)
# ---------------------------------------------------------------------------

_STUDENT_COURSES_CACHE_TIMEOUT = 1800  # 30 min


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


# ---------------------------------------------------------------------------
# StudentViewSet
# ---------------------------------------------------------------------------

class StudentViewSet(viewsets.GenericViewSet):
    """
    Student lifecycle endpoints.

    GET    /api/v1/students/                 — list (Admin, Principal)
    POST   /api/v1/students/                 — create student user + profile (Admin)
    GET    /api/v1/students/{id}/            — retrieve (Admin, Principal, own student)
    PATCH  /api/v1/students/{id}/            — update profile (Admin)
    DELETE /api/v1/students/{id}/            — soft-delete (Admin, Super Admin)
    POST   /api/v1/students/{id}/assign-program/   — assign program (Admin)
    POST   /api/v1/students/{id}/enroll-electives/ — enroll 4 electives (Admin)
    GET    /api/v1/students/{id}/courses/          — list enrollments (Admin, Teacher, own Student)
    """

    serializer_class = StudentProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['level', 'program', 'status']
    search_fields = ['user__first_name', 'user__last_name', 'user__school_id']
    ordering_fields = ['user__school_id', 'enrolled_date']

    def get_permissions(self):
        if self.action == 'list':
            return [IsAdminOrPrincipal()]
        if self.action in (
            'create', 'partial_update', 'destroy',
            'assign_program', 'enroll_electives',
        ):
            return [IsAdminOrSuperAdmin()]
        if self.action == 'retrieve':
            return [IsAdminOrPrincipalOrSelf()]
        if self.action == 'courses':
            return [CanViewStudentCourses()]
        if self.action == 'fees':
            return [IsAdminOrPrincipalOrSelf()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            StudentProfile.objects
            .select_related('user', 'level', 'program')
            .all()
        )

    def _get_student_profile(self, pk):
        """Return StudentProfile by pk (UUID of either StudentProfile or the user)."""
        try:
            return (
                StudentProfile.objects
                .select_related('user', 'level', 'program')
                .get(pk=pk)
            )
        except StudentProfile.DoesNotExist:
            return None

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(self, request):
        data = request.data
        required = ['first_name', 'last_name', 'password', 'level', 'enrolled_date']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return _err('Missing required fields.', {f: ['This field is required.'] for f in missing})

        try:
            from apps.academics.models import Level
            level = Level.objects.get(pk=data['level'])
        except Exception:
            return _err('Invalid level.', {'level': ['Level not found.']})

        try:
            user = UserService.create_user(
                first_name=data['first_name'],
                last_name=data['last_name'],
                email=data.get('email'),
                phone=data.get('phone'),
                password=data['password'],
                roles=['STUDENT'],
                created_by=request.user,
            )
        except Exception as exc:
            return _err(str(exc))

        program = None
        if data.get('program'):
            try:
                program = Program.objects.get(pk=data['program'])
            except Program.DoesNotExist:
                return _err('Invalid program.', {'program': ['Program not found.']})

        try:
            enrolled_date = datetime.date.fromisoformat(data['enrolled_date'])
        except (ValueError, TypeError):
            return _err('Invalid enrolled_date format. Use YYYY-MM-DD.')

        profile = StudentProfile.objects.create(
            user=user,
            level=level,
            program=program,
            class_section=data.get('class_section'),
            status=StudentProfile.ACTIVE,
            enrolled_date=enrolled_date,
        )

        return _ok(StudentProfileSerializer(profile).data, 'Student created.', status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # RETRIEVE
    # ------------------------------------------------------------------

    def retrieve(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, profile)
        return _ok(self.get_serializer(profile).data)

    # ------------------------------------------------------------------
    # PARTIAL UPDATE
    # ------------------------------------------------------------------

    def partial_update(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        if profile.status == StudentProfile.GRADUATED:
            return _err('Cannot modify a graduated student.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(serializer.data, 'Student updated.')

    # ------------------------------------------------------------------
    # SOFT DELETE
    # ------------------------------------------------------------------

    def destroy(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        profile.user.is_active = False
        profile.user.save(update_fields=['is_active'])
        profile.status = StudentProfile.INACTIVE
        profile.save(update_fields=['status'])

        return Response({'success': True, 'message': 'Student deactivated.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # ASSIGN PROGRAM
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='assign-program')
    def assign_program(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        if profile.status == StudentProfile.GRADUATED:
            return _err('Cannot modify a graduated student.', status_code=status.HTTP_403_FORBIDDEN)

        program_id = request.data.get('program_id')
        if not program_id:
            return _err('program_id is required.', {'program_id': ['This field is required.']})

        try:
            program = Program.objects.get(pk=program_id)
        except Program.DoesNotExist:
            return _err('Program not found.', status_code=status.HTTP_404_NOT_FOUND)

        profile.program = program
        profile.save(update_fields=['program'])

        # Signal fires on StudentProfile.save() only for created=True.
        # Re-triggering auto-core-enrollment here when program is assigned.
        current_term = Term.objects.filter(is_current=True).first()
        if current_term:
            EnrollmentService.enroll_core_courses(
                student=profile.user,
                term=current_term,
                level=profile.level,
            )

        cache.delete(f'student:{profile.user_id}:courses')
        return _ok(
            {'school_id': profile.user.school_id, 'program': program.get_name_display()},
            'Program assigned. Core courses enrolled.',
        )

    # ------------------------------------------------------------------
    # ENROLL ELECTIVES
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='enroll-electives')
    def enroll_electives(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        if profile.status == StudentProfile.GRADUATED:
            return _err('Cannot modify a graduated student.', status_code=status.HTTP_403_FORBIDDEN)

        course_ids = request.data.get('course_ids', [])

        current_term = Term.objects.filter(is_current=True).first()
        if current_term is None:
            return _err('No current term found. Cannot enroll electives.')

        try:
            count = EnrollmentService.enroll_electives(
                student=profile.user,
                course_ids=course_ids,
                term=current_term,
                level=profile.level,
                enrolled_by=request.user,
            )
        except ValueError as exc:
            return _err(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        cache.delete(f'student:{profile.user_id}:courses')
        return _ok({'enrolled': count}, f'Enrolled in {count} electives.')

    # ------------------------------------------------------------------
    # LIST COURSES (enrollments)
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='courses')
    def courses(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, profile)
        cache_key = f'student:{profile.user_id}:courses'
        cached = cache.get(cache_key)
        if cached is not None:
            return _ok(cached)
        enrollments = (
            Enrollment.objects
            .filter(student=profile.user)
            .select_related('course', 'term__academic_year', 'level')
        )
        data = EnrollmentSerializer(enrollments, many=True).data
        cache.set(cache_key, data, _STUDENT_COURSES_CACHE_TIMEOUT)
        return _ok(data)

    # ------------------------------------------------------------------
    # FEES
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='fees')
    def fees(self, request, pk=None):
        profile = self._get_student_profile(pk)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, profile)
        from apps.fees.models import StudentFee
        from apps.fees.serializers import StudentFeeSerializer
        student_fees = (
            StudentFee.objects
            .filter(student=profile.user)
            .select_related('term__academic_year')
            .prefetch_related('payments__recorded_by')
        )
        return _ok(StudentFeeSerializer(student_fees, many=True).data)
