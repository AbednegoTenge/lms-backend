import datetime

import factory
from factory.django import DjangoModelFactory

from apps.schedules.models import ClassTimetable, ExamSchedule, Holiday


class ClassTimetableFactory(DjangoModelFactory):
    class Meta:
        model = ClassTimetable

    course = factory.SubFactory('tests.factories.academics_factory.CourseFactory')
    teacher = factory.SubFactory('tests.factories.user_factory.UserFactory', role='TEACHER')
    level = factory.SubFactory('tests.factories.academics_factory.LevelFactory')
    class_section = '1A'
    term = factory.SubFactory('tests.factories.academics_factory.TermFactory')
    day_of_week = ClassTimetable.MON
    start_time = datetime.time(8, 0)
    end_time = datetime.time(9, 0)
    room = factory.Sequence(lambda n: f'Room {n + 1}')


class ExamScheduleFactory(DjangoModelFactory):
    class Meta:
        model = ExamSchedule

    course = factory.SubFactory('tests.factories.academics_factory.CourseFactory')
    level = factory.SubFactory('tests.factories.academics_factory.LevelFactory')
    term = factory.SubFactory('tests.factories.academics_factory.TermFactory')
    exam_date = datetime.date(2025, 11, 15)
    start_time = datetime.time(9, 0)
    end_time = datetime.time(11, 0)
    room = factory.Sequence(lambda n: f'Hall {n + 1}')
    exam_type = ExamSchedule.MID_TERM


class HolidayFactory(DjangoModelFactory):
    class Meta:
        model = Holiday

    name = factory.Sequence(lambda n: f'Holiday {n + 1}')
    start_date = datetime.date(2025, 12, 25)
    end_date = datetime.date(2026, 1, 2)
    academic_year = factory.SubFactory('tests.factories.academics_factory.AcademicYearFactory')
