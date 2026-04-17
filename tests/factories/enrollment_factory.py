import datetime

import factory
from factory.django import DjangoModelFactory

from apps.enrollment.models import Enrollment, StudentProfile


class StudentProfileFactory(DjangoModelFactory):
    class Meta:
        model = StudentProfile

    user = factory.SubFactory('tests.factories.user_factory.UserFactory', role='STUDENT')
    level = factory.SubFactory('tests.factories.academics_factory.LevelFactory', number=1)
    program = None
    class_section = None
    status = StudentProfile.ACTIVE
    enrolled_date = factory.LazyFunction(datetime.date.today)


class EnrollmentFactory(DjangoModelFactory):
    class Meta:
        model = Enrollment

    student = factory.SubFactory('tests.factories.user_factory.UserFactory', role='STUDENT')
    course = factory.SubFactory('tests.factories.academics_factory.CourseFactory')
    term = factory.SubFactory('tests.factories.academics_factory.TermFactory')
    level = factory.SubFactory('tests.factories.academics_factory.LevelFactory', number=1)
    enrollment_type = Enrollment.CORE
    enrolled_by = None
    is_active = True
