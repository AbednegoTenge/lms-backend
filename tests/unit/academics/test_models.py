import datetime

import pytest

from apps.academics.models import AcademicYear, Course, Program, Term
from tests.factories import (
    AcademicYearFactory,
    CourseFactory,
    ElectiveCourseFactory,
    LevelFactory,
    ProgramFactory,
    TeacherCourseAssignmentFactory,
    TermFactory,
    WeeklyTopicFactory,
    CourseOutlineFactory,
)


# ---------------------------------------------------------------------------
# AcademicYear
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAcademicYear:
    def test_only_one_is_current(self):
        yr1 = AcademicYearFactory(is_current=True)
        yr2 = AcademicYearFactory(is_current=True)
        yr1.refresh_from_db()
        assert yr1.is_current is False
        assert yr2.is_current is True

    def test_setting_is_current_false_does_not_affect_others(self):
        yr1 = AcademicYearFactory(is_current=True)
        yr2 = AcademicYearFactory(is_current=False)
        yr2.is_current = False
        yr2.save()
        yr1.refresh_from_db()
        assert yr1.is_current is True

    def test_str(self):
        yr = AcademicYearFactory(name='2024/2025')
        assert str(yr) == '2024/2025'


# ---------------------------------------------------------------------------
# Term
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTerm:
    def test_unique_together_academic_year_term_number(self):
        from django.db import IntegrityError
        yr = AcademicYearFactory()
        TermFactory(academic_year=yr, term_number=1)
        with pytest.raises(IntegrityError):
            TermFactory(academic_year=yr, term_number=1)

    def test_same_term_number_allowed_in_different_years(self):
        yr1 = AcademicYearFactory()
        yr2 = AcademicYearFactory()
        t1 = TermFactory(academic_year=yr1, term_number=1)
        t2 = TermFactory(academic_year=yr2, term_number=1)
        assert t1.pk != t2.pk

    def test_str(self):
        yr = AcademicYearFactory(name='2024/2025')
        t = TermFactory(academic_year=yr, term_number=2)
        assert 'Term 2' in str(t)
        assert '2024/2025' in str(t)


# ---------------------------------------------------------------------------
# Level (seeded)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLevel:
    def test_seed_levels_exist(self):
        from apps.academics.models import Level
        assert Level.objects.filter(number=1).exists()
        assert Level.objects.filter(number=2).exists()
        assert Level.objects.filter(number=3).exists()

    def test_level_number_is_unique(self):
        from django.db import IntegrityError
        from apps.academics.models import Level
        # number=1 already exists from seed; creating again via direct ORM must fail
        with pytest.raises(IntegrityError):
            Level.objects.create(number=1, name='Duplicate')


# ---------------------------------------------------------------------------
# Program (seeded)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProgram:
    def test_seed_programs_exist(self):
        assert Program.objects.filter(name=Program.GENERAL_ARTS).exists()
        assert Program.objects.filter(name=Program.GENERAL_SCIENCE).exists()
        assert Program.objects.filter(name=Program.HOME_ECONOMICS).exists()
        assert Program.objects.filter(name=Program.BUSINESS).exists()
        assert Program.objects.filter(name=Program.VISUAL_ARTS).exists()

    def test_program_codes_unique(self):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            # GA already exists from seed
            Program.objects.create(name='GENERAL_ARTS', code='GA')

    def test_str_returns_display_name(self):
        p = Program.objects.get(name=Program.GENERAL_ARTS)
        assert str(p) == 'General Arts'


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCourse:
    def test_seed_core_courses_exist(self):
        assert Course.objects.filter(code='CMATH', course_type=Course.CORE).exists()
        assert Course.objects.filter(code='CENG', course_type=Course.CORE).exists()
        assert Course.objects.filter(code='CPHY', course_type=Course.CORE).exists()
        assert Course.objects.filter(code='CBIO', course_type=Course.CORE).exists()
        assert Course.objects.filter(code='CCHEM', course_type=Course.CORE).exists()
        assert Course.objects.filter(code='AGRIC', course_type=Course.CORE).exists()
        assert Course.objects.filter(code='SOCST', course_type=Course.CORE).exists()

    def test_core_course_has_no_program(self):
        c = CourseFactory(course_type=Course.CORE, program=None)
        assert c.program is None

    def test_elective_course_has_program(self):
        c = ElectiveCourseFactory()
        assert c.program is not None
        assert c.course_type == Course.ELECTIVE

    def test_code_unique(self):
        from django.db import IntegrityError
        CourseFactory(code='UNIQUE1')
        with pytest.raises(IntegrityError):
            CourseFactory(code='UNIQUE1')

    def test_str(self):
        # Use a code that doesn't collide with seeded core courses
        c = CourseFactory(code='TSTCRS', name='Test Course Name')
        assert 'TSTCRS' in str(c)
        assert 'Test Course Name' in str(c)


# ---------------------------------------------------------------------------
# TeacherCourseAssignment
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherCourseAssignment:
    def test_unique_together(self):
        from django.db import IntegrityError
        a = TeacherCourseAssignmentFactory()
        with pytest.raises(IntegrityError):
            TeacherCourseAssignmentFactory(
                teacher=a.teacher,
                course=a.course,
                term=a.term,
                level=a.level,
            )

    def test_str(self):
        a = TeacherCourseAssignmentFactory()
        s = str(a)
        assert a.teacher.school_id in s
        assert a.course.code in s


# ---------------------------------------------------------------------------
# CourseOutline + WeeklyTopic
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCourseOutlineAndWeeklyTopic:
    def test_weekly_topic_week_number_unique_per_outline(self):
        from django.db import IntegrityError
        outline = CourseOutlineFactory()
        WeeklyTopicFactory(outline=outline, week_number=1)
        with pytest.raises(IntegrityError):
            WeeklyTopicFactory(outline=outline, week_number=1)

    def test_same_week_number_allowed_in_different_outlines(self):
        o1 = CourseOutlineFactory()
        o2 = CourseOutlineFactory()
        t1 = WeeklyTopicFactory(outline=o1, week_number=1)
        t2 = WeeklyTopicFactory(outline=o2, week_number=1)
        assert t1.pk != t2.pk

    def test_outline_one_to_one_with_assignment(self):
        from django.db import IntegrityError
        from apps.academics.models import CourseOutline
        a = TeacherCourseAssignmentFactory()
        CourseOutline.objects.create(assignment=a)
        with pytest.raises(IntegrityError):
            CourseOutline.objects.create(assignment=a)
