import datetime

import factory
from factory.django import DjangoModelFactory

from apps.assessments.models import Question, QuestionChoice, Quiz, QuizAttempt, Resource


class ResourceFactory(DjangoModelFactory):
    class Meta:
        model = Resource

    assignment = factory.SubFactory(
        'tests.factories.academics_factory.TeacherCourseAssignmentFactory'
    )
    title = factory.Sequence(lambda n: f'Resource {n}')
    resource_type = Resource.VIDEO_LINK
    url = factory.Sequence(lambda n: f'https://www.youtube.com/watch?v=test{n:06d}')
    file = None


class PDFResourceFactory(ResourceFactory):
    resource_type = Resource.PDF
    url = None
    file = factory.django.FileField(filename='test.pdf', data=b'%PDF-1.4 fake pdf')


# ---------------------------------------------------------------------------
# Quiz factories
# ---------------------------------------------------------------------------

class QuizFactory(DjangoModelFactory):
    class Meta:
        model = Quiz

    assignment = factory.SubFactory(
        'tests.factories.academics_factory.TeacherCourseAssignmentFactory'
    )
    title = factory.Sequence(lambda n: f'Quiz {n}')
    instructions = None
    max_attempts = 1
    due_datetime = factory.LazyFunction(
        lambda: datetime.datetime(2099, 12, 31, 23, 59, 59,
                                  tzinfo=datetime.timezone.utc)
    )
    status = Quiz.DRAFT
    total_marks = factory.LazyFunction(lambda: 10)


class OpenQuizFactory(QuizFactory):
    status = Quiz.OPEN


class QuestionFactory(DjangoModelFactory):
    class Meta:
        model = Question

    quiz = factory.SubFactory(QuizFactory)
    question_text = factory.Sequence(lambda n: f'Question {n}?')
    question_type = Question.MULTIPLE_CHOICE
    marks = factory.LazyFunction(lambda: 2)
    order = factory.Sequence(lambda n: n + 1)


class QuestionChoiceFactory(DjangoModelFactory):
    class Meta:
        model = QuestionChoice

    question = factory.SubFactory(QuestionFactory)
    text = factory.Sequence(lambda n: f'Choice {n}')
    is_correct = False


class QuizAttemptFactory(DjangoModelFactory):
    class Meta:
        model = QuizAttempt

    quiz = factory.SubFactory(OpenQuizFactory)
    student = factory.SubFactory('tests.factories.user_factory.UserFactory', role='STUDENT')
    attempt_number = 1
    status = QuizAttempt.IN_PROGRESS
