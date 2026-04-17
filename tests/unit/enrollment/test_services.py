"""Unit tests for EnrollmentService."""
import datetime

import pytest

from apps.academics.models import Course
from apps.enrollment.models import Enrollment, StudentProfile
from apps.enrollment.services import EnrollmentService
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
# enroll_core_courses
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnrollCoreCourses:

    def test_creates_exactly_7_core_enrollments(self):
        """The seed data has 7 core courses; new student should get all 7."""
        level = LevelFactory(number=1)
        term = TermFactory(is_current=True)
        student = UserFactory(role='STUDENT')

        count = EnrollmentService.enroll_core_courses(
            student=student, term=term, level=level
        )

        # There are 7 seeded core courses from migration 0004
        db_count = Enrollment.objects.filter(student=student, enrollment_type=Enrollment.CORE).count()
        assert db_count == 7
        assert count == 7

    def test_enroll_core_courses_is_idempotent(self):
        """Calling enroll_core_courses twice must not create duplicates."""
        level = LevelFactory(number=1)
        term = TermFactory(is_current=True)
        student = UserFactory(role='STUDENT')

        EnrollmentService.enroll_core_courses(student=student, term=term, level=level)
        EnrollmentService.enroll_core_courses(student=student, term=term, level=level)

        db_count = Enrollment.objects.filter(student=student, enrollment_type=Enrollment.CORE).count()
        assert db_count == 7

    def test_no_enrollment_when_no_core_courses(self):
        """If all core courses are inactive, nothing is enrolled."""
        Course.objects.filter(course_type=Course.CORE).update(is_active=False)
        level = LevelFactory(number=1)
        term = TermFactory(is_current=True)
        student = UserFactory(role='STUDENT')

        count = EnrollmentService.enroll_core_courses(student=student, term=term, level=level)

        assert count == 0
        assert Enrollment.objects.filter(student=student).count() == 0


# ---------------------------------------------------------------------------
# enroll_electives
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnrollElectives:

    def _setup(self):
        program = ProgramFactory(name='GENERAL_ARTS', code='GA')
        level = LevelFactory(number=1)
        term = TermFactory(is_current=True)
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level, program=program)
        courses = [ElectiveCourseFactory(program=program) for _ in range(4)]
        return student, profile, program, level, term, courses

    def test_enroll_exactly_4_electives_succeeds(self):
        student, profile, program, level, term, courses = self._setup()
        course_ids = [str(c.pk) for c in courses]

        count = EnrollmentService.enroll_electives(
            student=student,
            course_ids=course_ids,
            term=term,
            level=level,
        )

        assert count == 4
        db_count = Enrollment.objects.filter(
            student=student,
            enrollment_type=Enrollment.ELECTIVE,
        ).count()
        assert db_count == 4

    def test_fewer_than_4_electives_raises(self):
        student, profile, program, level, term, courses = self._setup()

        with pytest.raises(ValueError, match='Exactly 4'):
            EnrollmentService.enroll_electives(
                student=student,
                course_ids=[str(courses[0].pk), str(courses[1].pk), str(courses[2].pk)],
                term=term,
                level=level,
            )

    def test_more_than_4_electives_raises(self):
        student, profile, program, level, term, courses = self._setup()
        extra = ElectiveCourseFactory(program=program)
        course_ids = [str(c.pk) for c in courses] + [str(extra.pk)]

        with pytest.raises(ValueError, match='Exactly 4'):
            EnrollmentService.enroll_electives(
                student=student,
                course_ids=course_ids,
                term=term,
                level=level,
            )

    def test_wrong_program_courses_raise(self):
        student, profile, program, level, term, courses = self._setup()
        other_program = ProgramFactory(name='BUSINESS', code='BUS')
        wrong = ElectiveCourseFactory(program=other_program)
        course_ids = [str(c.pk) for c in courses[:3]] + [str(wrong.pk)]

        with pytest.raises(ValueError, match="do not belong to the student's program"):
            EnrollmentService.enroll_electives(
                student=student,
                course_ids=course_ids,
                term=term,
                level=level,
            )

    def test_student_without_program_raises(self):
        level = LevelFactory(number=1)
        term = TermFactory(is_current=True)
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        program = ProgramFactory(name='GENERAL_ARTS', code='GA')
        courses = [ElectiveCourseFactory(program=program) for _ in range(4)]

        with pytest.raises(ValueError, match='does not have a program'):
            EnrollmentService.enroll_electives(
                student=student,
                course_ids=[str(c.pk) for c in courses],
                term=term,
                level=level,
            )

    def test_invalid_course_ids_raise(self):
        student, profile, program, level, term, courses = self._setup()
        bad_ids = [str(courses[0].pk), str(courses[1].pk), str(courses[2].pk), '00000000-0000-0000-0000-000000000000']

        with pytest.raises(ValueError, match='invalid or not active'):
            EnrollmentService.enroll_electives(
                student=student,
                course_ids=bad_ids,
                term=term,
                level=level,
            )


# ---------------------------------------------------------------------------
# Signal: auto-enroll on StudentProfile creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAutoEnrollSignal:

    def test_creating_student_profile_auto_enrolls_core_courses(self):
        """post_save signal fires and creates 7 core enrollments."""
        level = LevelFactory(number=1)
        yr = AcademicYearFactory(is_current=True)
        term = TermFactory(academic_year=yr, term_number=1, is_current=True)
        student = UserFactory(role='STUDENT')

        # Act — creating the profile triggers the signal
        StudentProfileFactory(user=student, level=level)

        count = Enrollment.objects.filter(student=student, enrollment_type=Enrollment.CORE).count()
        assert count == 7

    def test_signal_is_idempotent_on_re_trigger(self):
        """Manually calling enroll_core_courses again must not create duplicates."""
        level = LevelFactory(number=1)
        yr = AcademicYearFactory(is_current=True)
        term = TermFactory(academic_year=yr, term_number=1, is_current=True)
        student = UserFactory(role='STUDENT')

        StudentProfileFactory(user=student, level=level)

        # Manually call again (simulating a retry or second signal)
        EnrollmentService.enroll_core_courses(student=student, term=term, level=level)

        count = Enrollment.objects.filter(student=student, enrollment_type=Enrollment.CORE).count()
        assert count == 7

    def test_no_term_means_no_enrollment(self):
        """If there is no current term the signal silently skips enrollment."""
        level = LevelFactory(number=1)
        student = UserFactory(role='STUDENT')

        StudentProfileFactory(user=student, level=level)

        count = Enrollment.objects.filter(student=student).count()
        assert count == 0
