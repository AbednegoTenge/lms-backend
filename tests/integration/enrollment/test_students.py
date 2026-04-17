"""Integration tests for student endpoints."""
import datetime

import pytest
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academics.models import Course
from apps.enrollment.models import Enrollment, StudentProfile
from tests.factories import (
    AcademicYearFactory,
    CourseFactory,
    ElectiveCourseFactory,
    LevelFactory,
    ProgramFactory,
    StudentProfileFactory,
    TermFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


STUDENTS_URL = '/api/v1/students/'


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentListPermissions:

    def test_unauthenticated_cannot_list(self, api_client):
        res = api_client.get(STUDENTS_URL)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_can_list(self, admin_user):
        client = auth_client(admin_user)
        res = client.get(STUDENTS_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_principal_can_list(self, db):
        principal = UserFactory(role='PRINCIPAL')
        client = auth_client(principal)
        res = client.get(STUDENTS_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_teacher_cannot_list(self, teacher_user):
        client = auth_client(teacher_user)
        res = client.get(STUDENTS_URL)
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_list(self, student_user):
        client = auth_client(student_user)
        res = client.get(STUDENTS_URL)
        assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Create student
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCreateStudent:

    def _payload(self, level_pk):
        return {
            'first_name': 'Kofi',
            'last_name': 'Mensah',
            'email': 'kofi@test.com',
            'password': 'TempPass123!',
            'level': str(level_pk),
            'enrolled_date': '2024-09-01',
        }

    def test_admin_can_create_student(self, admin_user):
        level = LevelFactory(number=1)
        client = auth_client(admin_user)
        res = client.post(STUDENTS_URL, self._payload(level.pk), format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['success'] is True
        assert 'school_id' in res.data['data']
        school_id = res.data['data']['school_id']
        assert school_id.startswith('STD')

    def test_student_cannot_create_student(self, student_user):
        level = LevelFactory(number=1)
        client = auth_client(student_user)
        res = client.post(STUDENTS_URL, self._payload(level.pk), format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_create_student(self, teacher_user):
        level = LevelFactory(number=1)
        client = auth_client(teacher_user)
        res = client.post(STUDENTS_URL, self._payload(level.pk), format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_create_student_missing_required_field(self, admin_user):
        level = LevelFactory(number=1)
        client = auth_client(admin_user)
        payload = self._payload(level.pk)
        del payload['password']
        res = client.post(STUDENTS_URL, payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_student_triggers_core_enrollment(self, admin_user):
        """POST /students/ → profile created → signal → 7 core enrollments."""
        level = LevelFactory(number=1)
        yr = AcademicYearFactory(is_current=True)
        TermFactory(academic_year=yr, term_number=1, is_current=True)

        client = auth_client(admin_user)
        res = client.post(STUDENTS_URL, self._payload(level.pk), format='json')
        assert res.status_code == status.HTTP_201_CREATED

        student_profile_id = res.data['data']['id']
        profile = StudentProfile.objects.get(pk=student_profile_id)
        count = Enrollment.objects.filter(
            student=profile.user,
            enrollment_type=Enrollment.CORE,
        ).count()
        assert count == 7


# ---------------------------------------------------------------------------
# Retrieve student
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRetrieveStudent:

    def test_admin_can_retrieve_any_student(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level)
        client = auth_client(admin_user)
        res = client.get(f'{STUDENTS_URL}{profile.pk}/')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['data']['school_id'] == profile.user.school_id

    def test_student_can_retrieve_own(self, db):
        level = LevelFactory(number=1)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level)
        client = auth_client(student)
        res = client.get(f'{STUDENTS_URL}{profile.pk}/')
        assert res.status_code == status.HTTP_200_OK

    def test_student_cannot_retrieve_another_student(self, db):
        level = LevelFactory(number=1)
        student_a = UserFactory(role='STUDENT')
        profile_a = StudentProfileFactory(user=student_a, level=level)
        student_b = UserFactory(role='STUDENT')
        client = auth_client(student_b)
        res = client.get(f'{STUDENTS_URL}{profile_a.pk}/')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_retrieve_nonexistent_returns_404(self, admin_user):
        client = auth_client(admin_user)
        res = client.get(f'{STUDENTS_URL}00000000-0000-0000-0000-000000000000/')
        assert res.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Update student
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUpdateStudent:

    def test_admin_can_patch_class_section(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level)
        client = auth_client(admin_user)
        res = client.patch(f'{STUDENTS_URL}{profile.pk}/', {'class_section': '1A'}, format='json')
        assert res.status_code == status.HTTP_200_OK
        profile.refresh_from_db()
        assert profile.class_section == '1A'

    def test_student_cannot_patch(self, db):
        level = LevelFactory(number=1)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level)
        client = auth_client(student)
        res = client.patch(f'{STUDENTS_URL}{profile.pk}/', {'class_section': '1A'}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeleteStudent:

    def test_admin_can_soft_delete_student(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level)
        client = auth_client(admin_user)
        res = client.delete(f'{STUDENTS_URL}{profile.pk}/')
        assert res.status_code == status.HTTP_204_NO_CONTENT
        profile.refresh_from_db()
        assert profile.status == StudentProfile.INACTIVE
        profile.user.refresh_from_db()
        assert profile.user.is_active is False

    def test_teacher_cannot_delete_student(self, teacher_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level)
        client = auth_client(teacher_user)
        res = client.delete(f'{STUDENTS_URL}{profile.pk}/')
        assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Assign program
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignProgram:

    def test_admin_assigns_program(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level, program=None)
        program = ProgramFactory(name='GENERAL_ARTS', code='GA')
        yr = AcademicYearFactory(is_current=True)
        TermFactory(academic_year=yr, term_number=1, is_current=True)

        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/assign-program/',
            {'program_id': str(program.pk)},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        profile.refresh_from_db()
        assert profile.program_id == program.pk

    def test_assign_program_with_invalid_id_returns_404(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level, program=None)
        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/assign-program/',
            {'program_id': '00000000-0000-0000-0000-000000000000'},
            format='json',
        )
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_program_missing_program_id(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level, program=None)
        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/assign-program/',
            {},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_cannot_assign_program(self, db):
        level = LevelFactory(number=1)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level, program=None)
        program = ProgramFactory(name='GENERAL_ARTS', code='GA')
        client = auth_client(student)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/assign-program/',
            {'program_id': str(program.pk)},
            format='json',
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Enroll electives
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnrollElectives:

    def _setup(self):
        program = ProgramFactory(name='GENERAL_ARTS', code='GA')
        level = LevelFactory(number=1)
        yr = AcademicYearFactory(is_current=True)
        term = TermFactory(academic_year=yr, term_number=1, is_current=True)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level, program=program)
        courses = [ElectiveCourseFactory(program=program) for _ in range(4)]
        return student, profile, program, level, term, courses

    def test_admin_enrolls_4_electives(self, admin_user):
        student, profile, program, level, term, courses = self._setup()
        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/enroll-electives/',
            {'course_ids': [str(c.pk) for c in courses]},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        assert res.data['data']['enrolled'] == 4

    def test_fewer_than_4_courses_returns_400(self, admin_user):
        student, profile, program, level, term, courses = self._setup()
        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/enroll-electives/',
            {'course_ids': [str(c.pk) for c in courses[:3]]},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_more_than_4_courses_returns_400(self, admin_user):
        _, profile, program, level, term, courses = self._setup()
        extra = ElectiveCourseFactory(program=program)
        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/enroll-electives/',
            {'course_ids': [str(c.pk) for c in courses] + [str(extra.pk)]},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_wrong_program_courses_returns_400(self, admin_user):
        student, profile, program, level, term, courses = self._setup()
        other_program = ProgramFactory(name='BUSINESS', code='BUS')
        wrong = ElectiveCourseFactory(program=other_program)
        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/enroll-electives/',
            {'course_ids': [str(c.pk) for c in courses[:3]] + [str(wrong.pk)]},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_cannot_enroll_own_electives(self, db):
        student, profile, program, level, term, courses = self._setup()
        client = auth_client(student)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/enroll-electives/',
            {'course_ids': [str(c.pk) for c in courses]},
            format='json',
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_no_current_term_returns_400(self, admin_user):
        """If there is no current term, enrollment should return a 400."""
        program = ProgramFactory(name='HOME_ECONOMICS', code='HE')
        level = LevelFactory(number=2)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level, program=program)
        courses = [ElectiveCourseFactory(program=program) for _ in range(4)]

        client = auth_client(admin_user)
        res = client.post(
            f'{STUDENTS_URL}{profile.pk}/enroll-electives/',
            {'course_ids': [str(c.pk) for c in courses]},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Student courses list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentCourses:

    def test_admin_can_list_student_courses(self, admin_user):
        level = LevelFactory(number=1)
        profile = StudentProfileFactory(level=level)
        client = auth_client(admin_user)
        res = client.get(f'{STUDENTS_URL}{profile.pk}/courses/')
        assert res.status_code == status.HTTP_200_OK
        assert isinstance(res.data['data'], list)

    def test_student_can_view_own_courses(self, db):
        level = LevelFactory(number=1)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level)
        client = auth_client(student)
        res = client.get(f'{STUDENTS_URL}{profile.pk}/courses/')
        assert res.status_code == status.HTTP_200_OK

    def test_student_cannot_view_another_students_courses(self, db):
        level = LevelFactory(number=1)
        profile_a = StudentProfileFactory(level=level)
        student_b = UserFactory(role='STUDENT')
        client = auth_client(student_b)
        res = client.get(f'{STUDENTS_URL}{profile_a.pk}/courses/')
        # student_b is not profile_a and not admin-like, but IS a teacher-role-free student
        # The view allows teachers — student_b is not teacher either
        assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# N+1 check
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentListNPlusOne:

    def test_list_50_students_no_n_plus_one(self, admin_user):
        """GET /students/ with 50 students must return correct results without N+1 queries.

        The queryset uses select_related('user', 'level', 'program') so user,
        level and program are fetched in one JOIN — no per-row extra queries.
        We verify this by asserting the response is correct and that query count
        doesn't grow: 1 student vs 50 students should execute the same queries.
        """
        from django.db import connection, reset_queries
        from django.test.utils import override_settings

        level = LevelFactory(number=1)
        program = ProgramFactory(name='GENERAL_ARTS', code='GA')

        # Warm up: 1 student baseline
        StudentProfileFactory(level=level, program=program)
        client = auth_client(admin_user)

        with override_settings(DEBUG=True):
            reset_queries()
            res = client.get(STUDENTS_URL + '?page_size=100')
            assert res.status_code == status.HTTP_200_OK
            one_count = len(connection.queries)

        # Add 49 more students (50 total)
        for _ in range(49):
            StudentProfileFactory(level=level, program=program)

        with override_settings(DEBUG=True):
            reset_queries()
            res50 = client.get(STUDENTS_URL + '?page_size=100')
            assert res50.status_code == status.HTTP_200_OK
            fifty_count = len(connection.queries)

        # Query count must stay bounded — allow at most 2 extra queries
        # (e.g. pagination count query may vary). Must NOT be 50 more.
        assert fifty_count <= one_count + 2, (
            f'N+1 detected: 1 student → {one_count} queries, '
            f'50 students → {fifty_count} queries'
        )

    def _extract_results(self, data):
        """Handle both paginated and non-paginated response shapes."""
        if isinstance(data, list):
            return data
        # paginated: {"count": N, "next": ..., "results": {"success": true, "data": [...]}}
        if 'results' in data:
            inner = data['results']
            return inner.get('data', inner) if isinstance(inner, dict) else inner
        return data

    def test_list_filters_by_level(self, admin_user):
        level1 = LevelFactory(number=1)
        level2 = LevelFactory(number=2)
        StudentProfileFactory(level=level1)
        StudentProfileFactory(level=level2)
        client = auth_client(admin_user)
        res = client.get(f'{STUDENTS_URL}?level={level1.pk}')
        assert res.status_code == status.HTTP_200_OK
        results = self._extract_results(res.data['data'])
        assert len(results) == 1
        assert str(results[0]['level']) == str(level1.pk)

    def test_list_filters_by_status(self, admin_user):
        level = LevelFactory(number=1)
        StudentProfileFactory(level=level, status=StudentProfile.ACTIVE)
        StudentProfileFactory(level=level, status=StudentProfile.INACTIVE)
        client = auth_client(admin_user)
        res = client.get(f'{STUDENTS_URL}?status=INACTIVE')
        assert res.status_code == status.HTTP_200_OK
        results = self._extract_results(res.data['data'])
        assert len(results) == 1
        assert results[0]['status'] == 'INACTIVE'
