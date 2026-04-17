import pytest
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academics.models import Course, TeacherCourseAssignment
from tests.factories import (
    AcademicYearFactory,
    CourseFactory,
    ElectiveCourseFactory,
    LevelFactory,
    ProgramFactory,
    TeacherCourseAssignmentFactory,
    TermFactory,
    UserFactory,
)


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


COURSES_URL = '/api/v1/courses/'


# ---------------------------------------------------------------------------
# Course CRUD permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCoursePermissions:
    def test_unauthenticated_cannot_list(self, api_client):
        res = api_client.get(COURSES_URL)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_can_list_courses(self, student_user):
        client = auth_client(student_user)
        res = client.get(COURSES_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_teacher_can_list_courses(self, teacher_user):
        client = auth_client(teacher_user)
        res = client.get(COURSES_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_student_cannot_create_course(self, student_user):
        client = auth_client(student_user)
        res = client.post(COURSES_URL, {
            'name': 'New Course', 'code': 'NC001', 'course_type': 'CORE',
        }, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create_course(self, admin_user):
        client = auth_client(admin_user)
        res = client.post(COURSES_URL, {
            'name': 'New Core Course', 'code': 'NCC001', 'course_type': 'CORE',
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['success'] is True

    def test_admin_can_delete_course(self, admin_user, db):
        course = CourseFactory()
        client = auth_client(admin_user)
        res = client.delete(f'{COURSES_URL}{course.pk}/')
        assert res.status_code == status.HTTP_204_NO_CONTENT

    def test_student_cannot_delete_course(self, student_user, db):
        course = CourseFactory()
        client = auth_client(student_user)
        res = client.delete(f'{COURSES_URL}{course.pk}/')
        assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Course filtering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCourseFiltering:
    def test_filter_by_course_type_core(self, admin_user):
        CourseFactory(course_type=Course.CORE, code='TCORE1')
        ElectiveCourseFactory(code='TELEC1')
        client = auth_client(admin_user)
        res = client.get(f'{COURSES_URL}?course_type=CORE')
        assert res.status_code == status.HTTP_200_OK
        results = res.data['data']
        assert all(r['course_type'] == 'CORE' for r in results)

    def test_filter_by_course_type_elective(self, admin_user):
        ElectiveCourseFactory(code='TELEC2')
        client = auth_client(admin_user)
        res = client.get(f'{COURSES_URL}?course_type=ELECTIVE')
        results = res.data['data']
        assert all(r['course_type'] == 'ELECTIVE' for r in results)

    def test_filter_by_program(self, admin_user, db):
        program = Program = ProgramFactory(name='BUSINESS', code='BUS')
        ElectiveCourseFactory(code='BELEC1', program=program)
        ElectiveCourseFactory(code='BELEC2', program=program)
        other_program = ProgramFactory(name='VISUAL_ARTS', code='VA')
        ElectiveCourseFactory(code='VELEC1', program=other_program)

        client = auth_client(admin_user)
        res = client.get(f'{COURSES_URL}?program={program.pk}')
        results = res.data['data']
        assert len(results) == 2
        assert all(str(r['program']) == str(program.pk) for r in results)

    def test_search_by_name(self, admin_user, db):
        CourseFactory(name='Algebra Advanced', code='ALG01')
        CourseFactory(name='Biology Basics', code='BIO01')
        client = auth_client(admin_user)
        res = client.get(f'{COURSES_URL}?search=Algebra')
        results = res.data['data']
        assert any('Algebra' in r['name'] for r in results)
        assert not any('Biology' in r['name'] for r in results)

    def test_search_by_code(self, admin_user, db):
        CourseFactory(name='Physics Wave', code='PHYWAV')
        CourseFactory(name='Chemistry Org', code='CHEMORG')
        client = auth_client(admin_user)
        res = client.get(f'{COURSES_URL}?search=PHYWAV')
        results = res.data['data']
        assert any(r['code'] == 'PHYWAV' for r in results)


# ---------------------------------------------------------------------------
# Course validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCourseValidation:
    def test_core_course_with_program_rejected(self, admin_user, db):
        program = ProgramFactory(name='BUSINESS', code='BUS2')
        client = auth_client(admin_user)
        res = client.post(COURSES_URL, {
            'name': 'Bad Core', 'code': 'BADC01',
            'course_type': 'CORE', 'program': str(program.pk),
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_elective_course_without_program_rejected(self, admin_user):
        client = auth_client(admin_user)
        res = client.post(COURSES_URL, {
            'name': 'Bad Elective', 'code': 'BADE01',
            'course_type': 'ELECTIVE',
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_code_rejected(self, admin_user, db):
        CourseFactory(code='DUPCODE')
        client = auth_client(admin_user)
        res = client.post(COURSES_URL, {
            'name': 'Duplicate', 'code': 'DUPCODE', 'course_type': 'CORE',
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Program courses cache
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProgramCoursesCache:
    def test_cache_set_on_program_filter(self, admin_user, db):
        program = ProgramFactory(name='HOME_ECONOMICS', code='HE2')
        ElectiveCourseFactory(code='HEC01', program=program)
        client = auth_client(admin_user)

        cache_key = f'program:{program.pk}:courses'
        assert cache.get(cache_key) is None

        res = client.get(f'{COURSES_URL}?program={program.pk}')
        assert res.status_code == status.HTTP_200_OK

        cached = cache.get(cache_key)
        assert cached is not None
        assert len(cached) == 1

    def test_cache_hit_returns_same_data(self, admin_user, db):
        program = ProgramFactory(name='GENERAL_SCIENCE', code='GS2')
        ElectiveCourseFactory(code='GEC01', program=program)
        client = auth_client(admin_user)

        # First request populates cache
        res1 = client.get(f'{COURSES_URL}?program={program.pk}')
        data1 = res1.data['data']

        # Second request should hit cache
        res2 = client.get(f'{COURSES_URL}?program={program.pk}')
        data2 = res2.data['data']

        assert data1 == data2

    def test_cache_invalidated_on_create(self, admin_user, db):
        program = ProgramFactory(name='VISUAL_ARTS', code='VA2')
        cache_key = f'program:{program.pk}:courses'
        cache.set(cache_key, [{'stale': True}], 3600)

        client = auth_client(admin_user)
        client.post(COURSES_URL, {
            'name': 'New Elective', 'code': 'VAELEC01',
            'course_type': 'ELECTIVE', 'program': str(program.pk),
        }, format='json')

        assert cache.get(cache_key) is None

    def test_cache_invalidated_on_delete(self, admin_user, db):
        program = ProgramFactory(name='BUSINESS', code='BUS3')
        course = ElectiveCourseFactory(code='BUSDEL01', program=program)
        cache_key = f'program:{program.pk}:courses'
        cache.set(cache_key, [{'stale': True}], 3600)

        client = auth_client(admin_user)
        client.delete(f'{COURSES_URL}{course.pk}/')
        assert cache.get(cache_key) is None


# ---------------------------------------------------------------------------
# Teacher assignment endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignTeacher:
    def test_admin_can_assign_teacher(self, admin_user, db):
        teacher = UserFactory(role='TEACHER')
        course = CourseFactory(code='TCRS001')
        yr = AcademicYearFactory()
        term = TermFactory(academic_year=yr, term_number=1)
        level = LevelFactory(number=1)

        client = auth_client(admin_user)
        res = client.post(f'{COURSES_URL}{course.pk}/assign-teacher/', {
            'teacher_id': str(teacher.pk),
            'term_id': str(term.pk),
            'level_id': str(level.pk),
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert 'assignment_id' in res.data['data']

    def test_student_cannot_assign_teacher(self, student_user, db):
        teacher = UserFactory(role='TEACHER')
        course = CourseFactory(code='TCRS002')
        yr = AcademicYearFactory()
        term = TermFactory(academic_year=yr, term_number=1)
        level = LevelFactory(number=2)

        client = auth_client(student_user)
        res = client.post(f'{COURSES_URL}{course.pk}/assign-teacher/', {
            'teacher_id': str(teacher.pk),
            'term_id': str(term.pk),
            'level_id': str(level.pk),
        }, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_assignment_rejected(self, admin_user, db):
        existing = TeacherCourseAssignmentFactory()
        client = auth_client(admin_user)
        res = client.post(f'{COURSES_URL}{existing.course.pk}/assign-teacher/', {
            'teacher_id': str(existing.teacher.pk),
            'term_id': str(existing.term.pk),
            'level_id': str(existing.level.pk),
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------

TERMS_URL = '/api/v1/terms/'


@pytest.mark.django_db
class TestTermCRUD:
    def test_admin_creates_term(self, admin_user, db):
        yr = AcademicYearFactory()
        client = auth_client(admin_user)
        res = client.post(TERMS_URL, {
            'academic_year': str(yr.pk),
            'term_number': 1,
            'start_date': '2025-09-01',
            'end_date': '2025-12-15',
            'is_current': False,
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['data']['term_number'] == 1

    def test_duplicate_term_in_year_rejected(self, admin_user, db):
        yr = AcademicYearFactory()
        TermFactory(academic_year=yr, term_number=1)
        client = auth_client(admin_user)
        res = client.post(TERMS_URL, {
            'academic_year': str(yr.pk),
            'term_number': 1,
            'start_date': '2025-09-01',
            'end_date': '2025-12-15',
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_can_list_terms(self, student_user, db):
        yr = AcademicYearFactory()
        TermFactory(academic_year=yr, term_number=1)
        client = auth_client(student_user)
        res = client.get(TERMS_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_student_cannot_create_term(self, student_user, db):
        yr = AcademicYearFactory()
        client = auth_client(student_user)
        res = client.post(TERMS_URL, {
            'academic_year': str(yr.pk),
            'term_number': 2,
            'start_date': '2025-01-01',
            'end_date': '2025-04-30',
        }, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_start_end_dates(self, admin_user, db):
        yr = AcademicYearFactory()
        client = auth_client(admin_user)
        res = client.post(TERMS_URL, {
            'academic_year': str(yr.pk),
            'term_number': 3,
            'start_date': '2025-06-01',
            'end_date': '2025-01-01',
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Levels and Programs (read-only)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLevelsAndPrograms:
    def test_list_levels_returns_three(self, student_user):
        client = auth_client(student_user)
        res = client.get('/api/v1/levels/')
        assert res.status_code == status.HTTP_200_OK
        data = res.data['data']
        assert len(data) == 3

    def test_list_programs_returns_five(self, student_user):
        client = auth_client(student_user)
        res = client.get('/api/v1/programs/')
        assert res.status_code == status.HTTP_200_OK
        data = res.data['data']
        assert len(data) == 5

    def test_unauthenticated_cannot_list_levels(self, api_client):
        res = api_client.get('/api/v1/levels/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
