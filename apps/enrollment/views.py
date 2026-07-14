import datetime

from django.core.cache import cache
from django.db.models import Count, OuterRef, Prefetch, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.academics.models import Program, TeacherCourseAssignment, Term
from apps.announcements.models import Announcement, AnnouncementRecipient
from apps.announcements.serializers import AnnouncementSerializer
from apps.assessments.models import Assignment, AssignmentSubmission
from apps.enrollment.models import Enrollment, SchoolClass, StudentProfile
from apps.enrollment.serializers import (
    EnrollmentSerializer,
    SchoolClassSerializer,
    StudentProfileSerializer,
)
from apps.enrollment.services import EnrollmentService
from apps.users.models import AuditLog, CustomUser, Role, UserRole
from apps.users.permissions import (
    CanViewStudentCourses,
    IsAdminOrPrincipal,
    IsAdminOrPrincipalOrTeacher,
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


def _build_teacher_map(enrollments, school_class_id):
    """
    One query fetching every TeacherCourseAssignment relevant to a list of
    enrollments, keyed the way EnrollmentSerializer.get_teacher() expects.
    Avoids the serializer's per-row fallback query (N+1).
    """
    keys = {(e.course_id, e.term_id, e.level_id) for e in enrollments}
    if not keys:
        return {}
    assignments = (
        TeacherCourseAssignment.objects
        .filter(
            course_id__in={k[0] for k in keys},
            term_id__in={k[1] for k in keys},
            level_id__in={k[2] for k in keys},
            school_class_id=school_class_id,
            is_active=True,
        )
        .select_related('teacher')
    )
    return {
        (a.course_id, a.term_id, a.level_id, school_class_id): a
        for a in assignments
    }


# ---------------------------------------------------------------------------
# SchoolClassViewSet
# ---------------------------------------------------------------------------

class SchoolClassViewSet(viewsets.GenericViewSet):
    """
    GET    /api/v1/classes/       - list classes
    POST   /api/v1/classes/       - create class
    GET    /api/v1/classes/{id}/  - retrieve class
    PATCH  /api/v1/classes/{id}/  - update class
    DELETE /api/v1/classes/{id}/  - delete class
    """

    serializer_class = SchoolClassSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['level', 'program', 'class_teacher', 'is_active']
    search_fields = [
        'name',
        'level__name',
        'program__name',
        'program__code',
        'class_teacher__school_id',
        'class_teacher__first_name',
        'class_teacher__last_name',
    ]
    ordering_fields = ['name', 'level__number', 'capacity', 'created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAdminOrPrincipalOrTeacher()]
        return [IsAdminOrSuperAdmin()]

    def get_queryset(self):
        return (
            SchoolClass.objects
            .select_related('level', 'program', 'class_teacher')
            .annotate(student_count=Count('student_profiles'))
            .all()
        )

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        obj = serializer.save()
        AuditLog.objects.create(
            user=request.user, action=AuditLog.CREATE,
            model_name='SchoolClass', object_id=obj.id,
            diff={'name': [None, obj.name]},
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return _ok(serializer.data, 'Class created.', status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return _ok(self.get_serializer(self.get_object()).data)

    def partial_update(self, request, pk=None):
        school_class = self.get_object()
        serializer = self.get_serializer(school_class, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        AuditLog.objects.create(
            user=request.user, action=AuditLog.UPDATE,
            model_name='SchoolClass', object_id=school_class.id,
            diff={f: request.data[f] for f in request.data},
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return _ok(serializer.data, 'Class updated.')

    def destroy(self, request, pk=None):
        obj = self.get_object()
        obj_id = obj.id
        obj.delete()
        AuditLog.objects.create(
            user=request.user, action=AuditLog.DELETE,
            model_name='SchoolClass', object_id=obj_id,
            diff={},
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(
            {'success': True, 'message': 'Class deleted.', 'data': {}},
            status=status.HTTP_204_NO_CONTENT,
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
    GET    /api/v1/students/{id}/dashboard/        — courses + assignments + announcements (Admin, Teacher, own Student)
    """

    serializer_class = StudentProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['level', 'program', 'school_class', 'status']
    search_fields = ['user__first_name', 'user__last_name', 'user__school_id', 'school_class__name']
    ordering_fields = ['user__school_id', 'enrolled_date']
    lookup_field = 'user__school_id'
    lookup_url_kwarg = 'school_id'

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
        if self.action in ('courses', 'dashboard'):
            return [CanViewStudentCourses()]
        if self.action == 'fees':
            return [IsAdminOrPrincipalOrSelf()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            StudentProfile.objects
            .select_related('user', 'level', 'program', 'school_class')
            .all()
        )

    def _get_student_profile(self, school_id):
        """Return StudentProfile by pk (UUID of either StudentProfile or the user)."""
        try:
            return (
                StudentProfile.objects
                .select_related('user', 'level', 'program', 'school_class')
                .get(user__school_id=school_id)
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

        school_class = None
        if data.get('school_class'):
            try:
                school_class = SchoolClass.objects.get(pk=data['school_class'], is_active=True)
            except SchoolClass.DoesNotExist:
                return _err('Invalid school_class.', {'school_class': ['Class not found.']})
            if school_class.level_id != level.id:
                return _err('Class level must match student level.', {'school_class': ['Invalid level for class.']})
            if program and school_class.program_id and school_class.program_id != program.id:
                return _err('Class program must match student program.', {'school_class': ['Invalid program for class.']})

        try:
            enrolled_date = datetime.date.fromisoformat(data['enrolled_date'])
        except (ValueError, TypeError):
            return _err('Invalid enrolled_date format. Use YYYY-MM-DD.')

        profile = StudentProfile.objects.create(
            user=user,
            level=level,
            program=program,
            school_class=school_class,
            class_section=data.get('class_section'),
            status=StudentProfile.ACTIVE,
            enrolled_date=enrolled_date,
        )

        return _ok(StudentProfileSerializer(profile).data, 'Student created.', status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # RETRIEVE
    # ------------------------------------------------------------------

    def retrieve(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
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
        AuditLog.objects.create(
            user=request.user, action=AuditLog.UPDATE,
            model_name='StudentProfile', object_id=profile.id,
            diff={f: request.data[f] for f in request.data},
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return _ok(serializer.data, 'Student updated.')

    # ------------------------------------------------------------------
    # SOFT DELETE
    # ------------------------------------------------------------------

    def destroy(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        if profile.status == StudentProfile.GRADUATED:
            return _err('Cannot modify a graduated student.', status_code=status.HTTP_403_FORBIDDEN)

        profile.user.is_active = False
        profile.user.save(update_fields=['is_active'])
        profile.status = StudentProfile.INACTIVE
        profile.save(update_fields=['status'])
        AuditLog.objects.create(
            user=request.user, action=AuditLog.DELETE,
            model_name='StudentProfile', object_id=profile.id,
            diff={'status': [StudentProfile.ACTIVE, StudentProfile.INACTIVE], 'is_active': [True, False]},
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        return Response({'success': True, 'message': 'Student deactivated.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # ASSIGN PROGRAM
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='assign-program')
    def assign_program(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
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

        old_program = profile.program.get_name_display() if profile.program else None
        profile.program = program
        # Enrollment logic must go through the StudentProfile signal, never a
        # direct service call from the view — the signal enrolls in current-term
        # core courses whenever this flag is set on a save.
        profile._enroll_core_courses = True
        profile.save(update_fields=['program'])

        AuditLog.objects.create(
            user=request.user, action=AuditLog.UPDATE,
            model_name='StudentProfile', object_id=profile.id,
            diff={'program': [old_program, program.get_name_display()]},
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        cache.delete(f'student:{profile.user_id}:courses:active')
        cache.delete(f'student:{profile.user_id}:courses:all')
        return _ok(
            {'school_id': profile.user.school_id, 'program': program.get_name_display()},
            'Program assigned. Core courses enrolled.',
        )

    # ------------------------------------------------------------------
    # ENROLL ELECTIVES
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='enroll-electives')
    def enroll_electives(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
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

        AuditLog.objects.create(
            user=request.user, action=AuditLog.CREATE,
            model_name='Enrollment', object_id=profile.id,
            diff={'course_ids': [None, course_ids]},
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        cache.delete(f'student:{profile.user_id}:courses:active')
        cache.delete(f'student:{profile.user_id}:courses:all')
        return _ok({'enrolled': count}, f'Enrolled in {count} electives.')

        
    # ------------------------------------------------------------------
    # LIST COURSES (enrollments)
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='courses')
    def courses(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, profile)

        include_inactive = request.query_params.get('include_inactive', 'false').lower() == 'true'
        cache_key = f'student:{profile.user_id}:courses:{"all" if include_inactive else "active"}'

        cached = cache.get(cache_key)
        if cached is not None:
            return _ok(cached)

        enrollments = (
            Enrollment.objects
            .filter(student=profile.user)
            .select_related('course', 'term__academic_year', 'level')
        )
        if not include_inactive:
            enrollments = enrollments.filter(is_active=True)
        enrollments = list(enrollments)

        teacher_map = _build_teacher_map(enrollments, profile.school_class_id)
        data = EnrollmentSerializer(
            enrollments, many=True,
            context={'teacher_map': teacher_map, 'school_class_id': profile.school_class_id},
        ).data
        cache.set(cache_key, data, _STUDENT_COURSES_CACHE_TIMEOUT)
        return _ok(data)

    # ------------------------------------------------------------------
    # DASHBOARD (enrolled courses + open assignments + announcements)
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='dashboard')
    def dashboard(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
        if profile is None:
            return _err('Student not found.', status_code=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, profile)
        student = profile.user

        enrollments = list(
            Enrollment.objects
            .filter(student=student, is_active=True)
            .select_related('course', 'term__academic_year', 'level')
        )
        teacher_map = _build_teacher_map(enrollments, profile.school_class_id)
        courses_data = EnrollmentSerializer(
            enrollments, many=True,
            context={'teacher_map': teacher_map, 'school_class_id': profile.school_class_id},
        ).data
        course_ids = [e.course_id for e in enrollments]

        assignments_qs = (
            Assignment.objects
            .filter(assignment__course_id__in=course_ids, status=Assignment.OPEN)
            .select_related('assignment__course')
            .prefetch_related(
                Prefetch(
                    'submissions',
                    queryset=AssignmentSubmission.objects.filter(student=student),
                    to_attr='student_submissions',
                )
            )
            .order_by('due_datetime')
        )
        assignments_data = [
            {
                'id': a.id,
                'course_name': a.assignment.course.name,
                'title': a.title,
                'due_datetime': a.due_datetime,
                'max_marks': a.max_marks,
                'status': a.status,
                'score': a.student_submissions[0].marks_obtained if a.student_submissions else None,
                'submission_status': a.student_submissions[0].status if a.student_submissions else None,
            }
            for a in assignments_qs
        ]

        announcements_qs = (
            Announcement.objects
            .filter(recipients__user=student)
            .select_related('created_by', 'program', 'level')
            .annotate(
                is_read=Subquery(
                    AnnouncementRecipient.objects.filter(
                        announcement=OuterRef('pk'), user=student,
                    ).values('is_read')[:1]
                )
            )
            .distinct()
            .order_by('-created_at')[:10]
        )
        announcements_data = AnnouncementSerializer(announcements_qs, many=True).data

        return _ok({
            'program_name': profile.program.get_name_display() if profile.program else None,
            'enrolled_courses': courses_data,
            'assignments': assignments_data,
            'announcements': announcements_data,
        })

    # ------------------------------------------------------------------
    # FEES
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='fees')
    def fees(self, request, school_id=None):
        profile = self._get_student_profile(school_id)
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
