import datetime

import factory
from factory.django import DjangoModelFactory

from apps.academics.models import (
    AcademicYear,
    Course,
    CourseOutline,
    Level,
    Program,
    TeacherCourseAssignment,
    Term,
    WeeklyTopic,
)


class AcademicYearFactory(DjangoModelFactory):
    class Meta:
        model = AcademicYear

    name = factory.Sequence(lambda n: f'{2020 + n}/{2021 + n}')
    start_date = factory.Sequence(lambda n: datetime.date(2020 + n, 9, 1))
    end_date = factory.Sequence(lambda n: datetime.date(2021 + n, 7, 31))
    is_current = False
    created_by = None


class TermFactory(DjangoModelFactory):
    class Meta:
        model = Term

    academic_year = factory.SubFactory(AcademicYearFactory)
    term_number = factory.Iterator([1, 2, 3])
    start_date = factory.Sequence(lambda n: datetime.date(2020, 9, 1) + datetime.timedelta(days=n * 100))
    end_date = factory.LazyAttribute(
        lambda obj: obj.start_date + datetime.timedelta(days=90)
    )
    is_current = False


class LevelFactory(DjangoModelFactory):
    class Meta:
        model = Level
        django_get_or_create = ('number',)

    number = 1
    name = factory.LazyAttribute(lambda obj: f'Level {obj.number} / Form {obj.number}')


class ProgramFactory(DjangoModelFactory):
    class Meta:
        model = Program
        django_get_or_create = ('name',)

    name = Program.GENERAL_ARTS
    code = 'GA'


class CourseFactory(DjangoModelFactory):
    class Meta:
        model = Course

    name = factory.Sequence(lambda n: f'Course {n}')
    code = factory.Sequence(lambda n: f'CRS{n:03d}')
    course_type = Course.CORE
    program = None
    is_active = True


class ElectiveCourseFactory(CourseFactory):
    course_type = Course.ELECTIVE
    program = factory.SubFactory(ProgramFactory)


class TeacherCourseAssignmentFactory(DjangoModelFactory):
    class Meta:
        model = TeacherCourseAssignment

    teacher = factory.SubFactory('tests.factories.user_factory.UserFactory', role='TEACHER')
    course = factory.SubFactory(CourseFactory)
    term = factory.SubFactory(TermFactory)
    level = factory.SubFactory(LevelFactory)
    is_active = True
    assigned_by = None


class CourseOutlineFactory(DjangoModelFactory):
    class Meta:
        model = CourseOutline

    assignment = factory.SubFactory(TeacherCourseAssignmentFactory)


class WeeklyTopicFactory(DjangoModelFactory):
    class Meta:
        model = WeeklyTopic

    outline = factory.SubFactory(CourseOutlineFactory)
    week_number = factory.Sequence(lambda n: (n % 14) + 1)
    title = factory.Sequence(lambda n: f'Week {(n % 14) + 1} Topic')
    description = factory.Faker('paragraph')
