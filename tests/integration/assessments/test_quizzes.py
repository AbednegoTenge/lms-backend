"""Integration tests for the full Quiz lifecycle (Phase 4)."""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.assessments.models import Question, Quiz, QuizAttempt
from tests.factories import (
    EnrollmentFactory,
    OpenQuizFactory,
    QuestionChoiceFactory,
    QuestionFactory,
    QuizAttemptFactory,
    QuizFactory,
    TeacherCourseAssignmentFactory,
    UserFactory,
)
from tests.conftest import get_tokens_for_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth(client, user):
    token, _ = get_tokens_for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


PAST = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
FUTURE = datetime.datetime(2099, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)


def make_quiz_payload(assignment, **overrides):
    payload = {
        'assignment': str(assignment.id),
        'title': 'Sample Quiz',
        'max_attempts': 1,
        'due_datetime': FUTURE.isoformat(),
        'total_marks': '10.00',
        'questions': [
            {
                'question_text': 'What is 2+2?',
                'question_type': 'MULTIPLE_CHOICE',
                'marks': '5.00',
                'order': 1,
                'choices': [
                    {'text': '3', 'is_correct': False},
                    {'text': '4', 'is_correct': True},
                ],
            },
            {
                'question_text': 'What is Python?',
                'question_type': 'SHORT_ANSWER',
                'marks': '5.00',
                'order': 2,
                'choices': [],
            },
        ],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Quiz Create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQuizCreate:
    def test_teacher_can_create_quiz_for_own_assignment(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        auth(api_client, teacher)

        resp = api_client.post(
            '/api/v1/quizzes/',
            make_quiz_payload(assignment),
            format='json',
        )
        assert resp.status_code == 201
        data = resp.json()['data']
        assert data['title'] == 'Sample Quiz'
        assert data['status'] == 'DRAFT'
        assert len(data['questions']) == 2

    def test_teacher_cannot_create_quiz_for_another_assignment(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        teacher_b = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher_b)
        auth(api_client, teacher_a)

        resp = api_client.post(
            '/api/v1/quizzes/',
            make_quiz_payload(assignment),
            format='json',
        )
        assert resp.status_code == 403

    def test_admin_can_create_quiz(self, api_client):
        admin = UserFactory(role='ADMIN')
        assignment = TeacherCourseAssignmentFactory()
        auth(api_client, admin)

        resp = api_client.post(
            '/api/v1/quizzes/',
            make_quiz_payload(assignment),
            format='json',
        )
        assert resp.status_code == 201

    def test_student_cannot_create_quiz(self, api_client):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        auth(api_client, student)

        resp = api_client.post(
            '/api/v1/quizzes/',
            make_quiz_payload(assignment),
            format='json',
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_create(self, api_client):
        assignment = TeacherCourseAssignmentFactory()
        resp = api_client.post(
            '/api/v1/quizzes/',
            make_quiz_payload(assignment),
            format='json',
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Quiz List
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQuizList:
    def test_admin_sees_all_quizzes(self, api_client):
        QuizFactory()
        QuizFactory()
        admin = UserFactory(role='ADMIN')
        auth(api_client, admin)

        resp = api_client.get('/api/v1/quizzes/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) >= 2

    def test_teacher_only_sees_own_quizzes(self, api_client):
        teacher = UserFactory(role='TEACHER')
        own_assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        QuizFactory(assignment=own_assignment)
        QuizFactory()  # different teacher

        auth(api_client, teacher)
        resp = api_client.get('/api/v1/quizzes/')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert len(data) == 1

    def test_student_cannot_list_quizzes(self, api_client):
        student = UserFactory(role='STUDENT')
        auth(api_client, student)

        resp = api_client.get('/api/v1/quizzes/')
        assert resp.status_code == 403

    def test_status_filter_works(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        QuizFactory(assignment=assignment, status=Quiz.DRAFT)
        QuizFactory(assignment=assignment, status=Quiz.OPEN)

        auth(api_client, teacher)
        resp = api_client.get('/api/v1/quizzes/?status=OPEN')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert all(q['status'] == 'OPEN' for q in data)


# ---------------------------------------------------------------------------
# Quiz Retrieve
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQuizRetrieve:
    def test_teacher_can_retrieve_own_quiz(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = QuizFactory(assignment=assignment)
        auth(api_client, teacher)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/')
        assert resp.status_code == 200

    def test_teacher_cannot_retrieve_other_quiz(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        quiz = QuizFactory(status=Quiz.DRAFT)  # belongs to teacher_b
        auth(api_client, teacher_a)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/')
        assert resp.status_code == 403

    def test_enrolled_student_can_retrieve_open_quiz(self, api_client):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        quiz = OpenQuizFactory(assignment=assignment)
        EnrollmentFactory(
            student=student,
            course=assignment.course,
            term=assignment.term,
            level=assignment.level,
        )
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/')
        assert resp.status_code == 200

    def test_unenrolled_student_cannot_retrieve_quiz(self, api_client):
        student = UserFactory(role='STUDENT')
        quiz = OpenQuizFactory()
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/')
        assert resp.status_code == 403

    def test_student_cannot_retrieve_draft_quiz(self, api_client):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        quiz = QuizFactory(assignment=assignment, status=Quiz.DRAFT)
        EnrollmentFactory(
            student=student,
            course=assignment.course,
            term=assignment.term,
            level=assignment.level,
        )
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Quiz Partial Update (DRAFT only)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQuizUpdate:
    def test_teacher_can_update_draft_quiz(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = QuizFactory(assignment=assignment, status=Quiz.DRAFT)
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/quizzes/{quiz.id}/',
            {'title': 'Updated Title', 'questions': []},
            format='json',
        )
        assert resp.status_code == 200
        assert resp.json()['data']['title'] == 'Updated Title'

    def test_cannot_update_open_quiz(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = OpenQuizFactory(assignment=assignment)
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/quizzes/{quiz.id}/',
            {'title': 'Hacked Title', 'questions': []},
            format='json',
        )
        assert resp.status_code == 422

    def test_other_teacher_cannot_update(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        quiz = QuizFactory(status=Quiz.DRAFT)
        auth(api_client, teacher_a)

        resp = api_client.patch(
            f'/api/v1/quizzes/{quiz.id}/',
            {'title': 'Injected', 'questions': []},
            format='json',
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Quiz Publish
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQuizPublish:
    def test_teacher_can_publish_draft_quiz(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = QuizFactory(assignment=assignment, status=Quiz.DRAFT)
        auth(api_client, teacher)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/publish/')
        assert resp.status_code == 200
        assert resp.json()['data']['status'] == 'OPEN'

    def test_cannot_publish_open_quiz_again(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = OpenQuizFactory(assignment=assignment)
        auth(api_client, teacher)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/publish/')
        assert resp.status_code == 422

    def test_other_teacher_cannot_publish(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        quiz = QuizFactory(status=Quiz.DRAFT)
        auth(api_client, teacher_a)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/publish/')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Start Attempt
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStartAttempt:
    def _setup_enrolled_student(self):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        quiz = OpenQuizFactory(assignment=assignment)
        EnrollmentFactory(
            student=student,
            course=assignment.course,
            term=assignment.term,
            level=assignment.level,
        )
        return student, quiz

    def test_enrolled_student_can_start_attempt(self, api_client):
        student, quiz = self._setup_enrolled_student()
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 201
        data = resp.json()['data']
        assert data['attempt_number'] == 1
        assert data['status'] == 'IN_PROGRESS'

    def test_unenrolled_student_gets_403(self, api_client):
        student = UserFactory(role='STUDENT')
        quiz = OpenQuizFactory()
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 403

    def test_teacher_cannot_start_attempt(self, api_client):
        teacher = UserFactory(role='TEACHER')
        quiz = OpenQuizFactory()
        auth(api_client, teacher)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 403

    def test_closed_quiz_returns_422(self, api_client):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        quiz = QuizFactory(assignment=assignment, status=Quiz.CLOSED)
        EnrollmentFactory(
            student=student,
            course=assignment.course,
            term=assignment.term,
            level=assignment.level,
        )
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 422

    def test_past_due_returns_422(self, api_client):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        quiz = QuizFactory(assignment=assignment, status=Quiz.OPEN, due_datetime=PAST)
        EnrollmentFactory(
            student=student,
            course=assignment.course,
            term=assignment.term,
            level=assignment.level,
        )
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 422

    def test_attempt_limit_enforced_422(self, api_client):
        student, quiz = self._setup_enrolled_student()
        quiz.max_attempts = 1
        quiz.save()

        # Create a completed attempt
        QuizAttemptFactory(
            quiz=quiz,
            student=student,
            attempt_number=1,
            status=QuizAttempt.GRADED,
        )
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 422

    def test_second_attempt_allowed_within_limit(self, api_client):
        student, quiz = self._setup_enrolled_student()
        quiz.max_attempts = 2
        quiz.save()

        QuizAttemptFactory(
            quiz=quiz,
            student=student,
            attempt_number=1,
            status=QuizAttempt.GRADED,
        )
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 201
        assert resp.json()['data']['attempt_number'] == 2

    def test_in_progress_attempt_returned_without_creating_new(self, api_client):
        student, quiz = self._setup_enrolled_student()
        existing = QuizAttemptFactory(
            quiz=quiz, student=student, attempt_number=1,
            status=QuizAttempt.IN_PROGRESS,
        )
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/quizzes/{quiz.id}/attempts/')
        assert resp.status_code == 200
        assert str(resp.json()['data']['id']) == str(existing.id)
        assert QuizAttempt.objects.filter(quiz=quiz, student=student).count() == 1


# ---------------------------------------------------------------------------
# Submit Attempt
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubmitAttempt:
    def _setup(self):
        student = UserFactory(role='STUDENT')
        assignment = TeacherCourseAssignmentFactory()
        quiz = OpenQuizFactory(assignment=assignment, total_marks=Decimal('10.00'))
        EnrollmentFactory(
            student=student,
            course=assignment.course,
            term=assignment.term,
            level=assignment.level,
        )
        q = QuestionFactory(
            quiz=quiz,
            question_type=Question.MULTIPLE_CHOICE,
            marks=Decimal('10.00'),
            order=1,
        )
        correct = QuestionChoiceFactory(question=q, is_correct=True)
        wrong = QuestionChoiceFactory(question=q, is_correct=False)
        attempt = QuizAttemptFactory(quiz=quiz, student=student, attempt_number=1)
        return student, quiz, q, correct, wrong, attempt

    def test_student_can_submit_correct_answer(self, api_client):
        student, quiz, q, correct, wrong, attempt = self._setup()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/quiz-attempts/{attempt.id}/submit/',
            {
                'answers': [
                    {
                        'question_id': str(q.id),
                        'selected_choice_ids': [str(correct.id)],
                    }
                ]
            },
            format='json',
        )
        assert resp.status_code == 200
        data = resp.json()['data']
        assert Decimal(data['score']) == Decimal('10.00')
        assert data['status'] == 'GRADED'

    def test_wrong_answer_gives_zero(self, api_client):
        student, quiz, q, correct, wrong, attempt = self._setup()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/quiz-attempts/{attempt.id}/submit/',
            {
                'answers': [
                    {
                        'question_id': str(q.id),
                        'selected_choice_ids': [str(wrong.id)],
                    }
                ]
            },
            format='json',
        )
        assert resp.status_code == 200
        data = resp.json()['data']
        assert Decimal(data['score']) == Decimal('0.00')

    def test_cannot_submit_already_submitted_attempt(self, api_client):
        student, quiz, q, correct, wrong, attempt = self._setup()
        attempt.status = QuizAttempt.SUBMITTED
        attempt.save()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/quiz-attempts/{attempt.id}/submit/',
            {'answers': []},
            format='json',
        )
        assert resp.status_code == 422

    def test_cannot_submit_other_students_attempt(self, api_client):
        student, quiz, q, correct, wrong, attempt = self._setup()
        other_student = UserFactory(role='STUDENT')
        auth(api_client, other_student)

        resp = api_client.post(
            f'/api/v1/quiz-attempts/{attempt.id}/submit/',
            {'answers': []},
            format='json',
        )
        assert resp.status_code == 404

    def test_submit_with_closed_quiz_returns_422(self, api_client):
        student, quiz, q, correct, wrong, attempt = self._setup()
        quiz.status = Quiz.CLOSED
        quiz.save()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/quiz-attempts/{attempt.id}/submit/',
            {'answers': []},
            format='json',
        )
        assert resp.status_code == 422

    def test_submit_past_due_returns_422(self, api_client):
        student, quiz, q, correct, wrong, attempt = self._setup()
        quiz.due_datetime = PAST
        quiz.save()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/quiz-attempts/{attempt.id}/submit/',
            {'answers': []},
            format='json',
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Submissions list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubmissions:
    def test_teacher_can_see_submissions(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = OpenQuizFactory(assignment=assignment)
        student = UserFactory(role='STUDENT')
        QuizAttemptFactory(
            quiz=quiz, student=student, attempt_number=1,
            status=QuizAttempt.GRADED,
        )
        auth(api_client, teacher)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/submissions/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) == 1

    def test_other_teacher_cannot_see_submissions(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        quiz = OpenQuizFactory()
        auth(api_client, teacher_a)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/submissions/')
        assert resp.status_code == 403

    def test_in_progress_attempts_excluded_from_submissions(self, api_client):
        teacher = UserFactory(role='TEACHER')
        assignment = TeacherCourseAssignmentFactory(teacher=teacher)
        quiz = OpenQuizFactory(assignment=assignment)
        QuizAttemptFactory(quiz=quiz, status=QuizAttempt.IN_PROGRESS)
        auth(api_client, teacher)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/submissions/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) == 0

    def test_student_cannot_see_submissions(self, api_client):
        student = UserFactory(role='STUDENT')
        quiz = OpenQuizFactory()
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/quizzes/{quiz.id}/submissions/')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Auto-close via Celery task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAutoClose:
    def test_close_expired_quizzes_task(self):
        from apps.assessments.tasks import close_expired_quizzes

        expired_quiz = OpenQuizFactory(due_datetime=PAST)
        still_open = OpenQuizFactory(due_datetime=FUTURE)
        draft_quiz = QuizFactory(status=Quiz.DRAFT, due_datetime=PAST)

        count = close_expired_quizzes()

        expired_quiz.refresh_from_db()
        still_open.refresh_from_db()
        draft_quiz.refresh_from_db()

        assert count == 1
        assert expired_quiz.status == Quiz.CLOSED
        assert still_open.status == Quiz.OPEN
        assert draft_quiz.status == Quiz.DRAFT  # draft not affected
