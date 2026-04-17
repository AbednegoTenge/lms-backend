"""Integration tests for the Assignment + TeacherEvaluation lifecycle (Phase 5)."""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.assessments.models import Assignment, AssignmentSubmission, TeacherEvaluation
from tests.factories import (
    AssignmentFactory,
    AssignmentSubmissionFactory,
    EnrollmentFactory,
    OpenAssignmentFactory,
    TeacherCourseAssignmentFactory,
    TeacherEvaluationFactory,
    UserFactory,
)
from tests.conftest import get_tokens_for_user

PAST = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
FUTURE = datetime.datetime(2099, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)


def auth(client, user):
    token, _ = get_tokens_for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def make_payload(course_assignment, **overrides):
    payload = {
        'assignment': str(course_assignment.id),
        'title': 'Week 1 Essay',
        'description': 'Write 500 words on photosynthesis.',
        'due_datetime': FUTURE.isoformat(),
        'submission_type': 'BOTH',
        'max_marks': '50.00',
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Assignment Create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentCreate:
    def test_teacher_can_create_assignment_for_own_course(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        auth(api_client, teacher)

        resp = api_client.post('/api/v1/course-assignments/', make_payload(ca), format='json')
        assert resp.status_code == 201
        data = resp.json()['data']
        assert data['title'] == 'Week 1 Essay'
        assert data['status'] == 'DRAFT'

    def test_teacher_cannot_create_assignment_for_other_course(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        teacher_b = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher_b)
        auth(api_client, teacher_a)

        resp = api_client.post('/api/v1/course-assignments/', make_payload(ca), format='json')
        assert resp.status_code == 403

    def test_student_cannot_create_assignment(self, api_client):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        auth(api_client, student)

        resp = api_client.post('/api/v1/course-assignments/', make_payload(ca), format='json')
        assert resp.status_code == 403

    def test_unauthenticated_cannot_create(self, api_client):
        ca = TeacherCourseAssignmentFactory()
        resp = api_client.post('/api/v1/course-assignments/', make_payload(ca), format='json')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Assignment List
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentList:
    def test_admin_sees_all_assignments(self, api_client):
        AssignmentFactory()
        AssignmentFactory()
        admin = UserFactory(role='ADMIN')
        auth(api_client, admin)

        resp = api_client.get('/api/v1/course-assignments/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) >= 2

    def test_teacher_sees_only_own_assignments(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        AssignmentFactory(assignment=ca)
        AssignmentFactory()  # different teacher

        auth(api_client, teacher)
        resp = api_client.get('/api/v1/course-assignments/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) == 1

    def test_student_sees_only_enrolled_open_assignments(self, api_client):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        EnrollmentFactory(
            student=student,
            course=ca.course,
            term=ca.term,
            level=ca.level,
        )
        OpenAssignmentFactory(assignment=ca)
        AssignmentFactory(assignment=ca, status=Assignment.DRAFT)  # draft — hidden
        OpenAssignmentFactory()  # different course — hidden

        auth(api_client, student)
        resp = api_client.get('/api/v1/course-assignments/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) == 1


# ---------------------------------------------------------------------------
# Assignment Retrieve
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentRetrieve:
    def test_teacher_can_retrieve_own_assignment(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = AssignmentFactory(assignment=ca)
        auth(api_client, teacher)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/')
        assert resp.status_code == 200

    def test_other_teacher_cannot_retrieve(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        obj = AssignmentFactory()
        auth(api_client, teacher_a)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/')
        assert resp.status_code == 403

    def test_enrolled_student_can_retrieve_open(self, api_client):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        obj = OpenAssignmentFactory(assignment=ca)
        EnrollmentFactory(student=student, course=ca.course, term=ca.term, level=ca.level)
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/')
        assert resp.status_code == 200

    def test_unenrolled_student_cannot_retrieve(self, api_client):
        student = UserFactory(role='STUDENT')
        obj = OpenAssignmentFactory()
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Assignment Partial Update (DRAFT only)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentUpdate:
    def test_teacher_can_update_draft(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = AssignmentFactory(assignment=ca, status=Assignment.DRAFT)
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/course-assignments/{obj.id}/',
            {'title': 'Updated Title'},
            format='json',
        )
        assert resp.status_code == 200
        assert resp.json()['data']['title'] == 'Updated Title'

    def test_cannot_update_open_assignment(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = OpenAssignmentFactory(assignment=ca)
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/course-assignments/{obj.id}/',
            {'title': 'Hacked'},
            format='json',
        )
        assert resp.status_code == 422

    def test_other_teacher_cannot_update(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        obj = AssignmentFactory(status=Assignment.DRAFT)
        auth(api_client, teacher_a)

        resp = api_client.patch(
            f'/api/v1/course-assignments/{obj.id}/',
            {'title': 'Injected'},
            format='json',
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentPublish:
    def test_teacher_can_publish_draft(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = AssignmentFactory(assignment=ca, status=Assignment.DRAFT)
        auth(api_client, teacher)

        resp = api_client.post(f'/api/v1/course-assignments/{obj.id}/publish/')
        assert resp.status_code == 200
        assert resp.json()['data']['status'] == 'OPEN'

    def test_cannot_publish_open_assignment(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = OpenAssignmentFactory(assignment=ca)
        auth(api_client, teacher)

        resp = api_client.post(f'/api/v1/course-assignments/{obj.id}/publish/')
        assert resp.status_code == 422

    def test_other_teacher_cannot_publish(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        obj = AssignmentFactory(status=Assignment.DRAFT)
        auth(api_client, teacher_a)

        resp = api_client.post(f'/api/v1/course-assignments/{obj.id}/publish/')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Student Submit
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentSubmit:
    def _setup(self):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        obj = OpenAssignmentFactory(assignment=ca, submission_type=Assignment.BOTH)
        EnrollmentFactory(student=student, course=ca.course, term=ca.term, level=ca.level)
        return student, obj

    def test_enrolled_student_can_submit(self, api_client):
        student, obj = self._setup()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/course-assignments/{obj.id}/submit/',
            {'text_content': 'My essay content.'},
        )
        assert resp.status_code == 201
        data = resp.json()['data']
        assert data['status'] == 'SUBMITTED'

    def test_unenrolled_student_cannot_submit(self, api_client):
        student = UserFactory(role='STUDENT')
        obj = OpenAssignmentFactory()
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/course-assignments/{obj.id}/submit/',
            {'text_content': 'Sneaky submission.'},
        )
        assert resp.status_code == 403

    def test_closed_assignment_returns_422(self, api_client):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        obj = AssignmentFactory(assignment=ca, status=Assignment.CLOSED)
        EnrollmentFactory(student=student, course=ca.course, term=ca.term, level=ca.level)
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/course-assignments/{obj.id}/submit/',
            {'text_content': 'Too late.'},
        )
        assert resp.status_code == 422

    def test_duplicate_submission_returns_409(self, api_client):
        student, obj = self._setup()
        AssignmentSubmissionFactory(assignment=obj, student=student)
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/course-assignments/{obj.id}/submit/',
            {'text_content': 'Second attempt.'},
        )
        assert resp.status_code == 409

    def test_late_submission_marked_late(self, api_client):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        obj = OpenAssignmentFactory(assignment=ca, due_datetime=PAST)
        EnrollmentFactory(student=student, course=ca.course, term=ca.term, level=ca.level)
        auth(api_client, student)

        resp = api_client.post(
            f'/api/v1/course-assignments/{obj.id}/submit/',
            {'text_content': 'Better late than never.'},
        )
        assert resp.status_code == 201
        assert resp.json()['data']['status'] == 'LATE'

    def test_text_only_assignment_requires_text_content(self, api_client):
        student = UserFactory(role='STUDENT')
        ca = TeacherCourseAssignmentFactory()
        obj = OpenAssignmentFactory(assignment=ca, submission_type=Assignment.TEXT)
        EnrollmentFactory(student=student, course=ca.course, term=ca.term, level=ca.level)
        auth(api_client, student)

        resp = api_client.post(f'/api/v1/course-assignments/{obj.id}/submit/', {})
        assert resp.status_code == 400

    def test_teacher_cannot_submit(self, api_client):
        teacher = UserFactory(role='TEACHER')
        obj = OpenAssignmentFactory()
        auth(api_client, teacher)

        resp = api_client.post(
            f'/api/v1/course-assignments/{obj.id}/submit/',
            {'text_content': 'Teachers cannot submit.'},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Submissions list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubmissionsList:
    def test_teacher_can_view_submissions(self, api_client):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = OpenAssignmentFactory(assignment=ca)
        AssignmentSubmissionFactory(assignment=obj)
        auth(api_client, teacher)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/submissions/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) == 1

    def test_other_teacher_cannot_view_submissions(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        obj = OpenAssignmentFactory()
        auth(api_client, teacher_a)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/submissions/')
        assert resp.status_code == 403

    def test_student_cannot_view_all_submissions(self, api_client):
        student = UserFactory(role='STUDENT')
        obj = OpenAssignmentFactory()
        auth(api_client, student)

        resp = api_client.get(f'/api/v1/course-assignments/{obj.id}/submissions/')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Grade submission
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGradeSubmission:
    def _setup(self):
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        obj = OpenAssignmentFactory(assignment=ca, max_marks=Decimal('100.00'))
        submission = AssignmentSubmissionFactory(assignment=obj)
        return teacher, submission

    def test_teacher_can_grade_submission(self, api_client):
        teacher, submission = self._setup()
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/assignment-submissions/{submission.id}/grade/',
            {'marks_obtained': '85.00', 'feedback': 'Good work!'},
            format='json',
        )
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['status'] == 'GRADED'
        assert Decimal(data['marks_obtained']) == Decimal('85.00')
        assert data['feedback'] == 'Good work!'

    def test_other_teacher_cannot_grade(self, api_client):
        teacher_a = UserFactory(role='TEACHER')
        _, submission = self._setup()
        auth(api_client, teacher_a)

        resp = api_client.patch(
            f'/api/v1/assignment-submissions/{submission.id}/grade/',
            {'marks_obtained': '50.00'},
            format='json',
        )
        assert resp.status_code == 403

    def test_marks_cannot_exceed_max(self, api_client):
        teacher, submission = self._setup()
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/assignment-submissions/{submission.id}/grade/',
            {'marks_obtained': '200.00'},
            format='json',
        )
        assert resp.status_code == 400

    def test_negative_marks_rejected(self, api_client):
        teacher, submission = self._setup()
        auth(api_client, teacher)

        resp = api_client.patch(
            f'/api/v1/assignment-submissions/{submission.id}/grade/',
            {'marks_obtained': '-5.00'},
            format='json',
        )
        assert resp.status_code == 400

    def test_student_cannot_grade(self, api_client):
        student = UserFactory(role='STUDENT')
        _, submission = self._setup()
        auth(api_client, student)

        resp = api_client.patch(
            f'/api/v1/assignment-submissions/{submission.id}/grade/',
            {'marks_obtained': '75.00'},
            format='json',
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Auto-close assignments via Celery task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAutoCloseAssignments:
    def test_close_expired_assignments_task(self):
        from apps.assessments.tasks import close_expired_assignments

        expired = OpenAssignmentFactory(due_datetime=PAST)
        still_open = OpenAssignmentFactory(due_datetime=FUTURE)
        draft = AssignmentFactory(status=Assignment.DRAFT, due_datetime=PAST)

        count = close_expired_assignments()

        expired.refresh_from_db()
        still_open.refresh_from_db()
        draft.refresh_from_db()

        assert count == 1
        assert expired.status == Assignment.CLOSED
        assert still_open.status == Assignment.OPEN
        assert draft.status == Assignment.DRAFT


# ---------------------------------------------------------------------------
# Teacher Evaluation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherEvaluation:
    def _setup_enrolled(self):
        student = UserFactory(role='STUDENT')
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        EnrollmentFactory(
            student=student,
            course=ca.course,
            term=ca.term,
            level=ca.level,
        )
        return student, teacher, ca

    def test_enrolled_student_can_submit_evaluation(self, api_client):
        student, teacher, ca = self._setup_enrolled()
        auth(api_client, student)

        resp = api_client.post(
            '/api/v1/evaluations/',
            {
                'teacher': str(teacher.id),
                'course': str(ca.course.id),
                'term': str(ca.term.id),
                'rating': 5,
                'comment': 'Excellent teacher.',
            },
            format='json',
        )
        assert resp.status_code == 201
        data = resp.json()['data']
        assert data['rating'] == 5

    def test_unenrolled_student_cannot_evaluate(self, api_client):
        student = UserFactory(role='STUDENT')
        teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=teacher)
        auth(api_client, student)

        resp = api_client.post(
            '/api/v1/evaluations/',
            {
                'teacher': str(teacher.id),
                'course': str(ca.course.id),
                'term': str(ca.term.id),
                'rating': 3,
            },
            format='json',
        )
        assert resp.status_code == 403

    def test_teacher_not_assigned_to_course_rejected(self, api_client):
        student = UserFactory(role='STUDENT')
        teacher_b = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory()  # belongs to teacher_a
        EnrollmentFactory(
            student=student,
            course=ca.course,
            term=ca.term,
            level=ca.level,
        )
        auth(api_client, student)

        resp = api_client.post(
            '/api/v1/evaluations/',
            {
                'teacher': str(teacher_b.id),
                'course': str(ca.course.id),
                'term': str(ca.term.id),
                'rating': 4,
            },
            format='json',
        )
        assert resp.status_code == 400

    def test_duplicate_evaluation_returns_409(self, api_client):
        student, teacher, ca = self._setup_enrolled()
        TeacherEvaluationFactory(
            student=student,
            teacher=teacher,
            course=ca.course,
            term=ca.term,
        )
        auth(api_client, student)

        resp = api_client.post(
            '/api/v1/evaluations/',
            {
                'teacher': str(teacher.id),
                'course': str(ca.course.id),
                'term': str(ca.term.id),
                'rating': 2,
            },
            format='json',
        )
        assert resp.status_code == 409

    def test_rating_out_of_range_rejected(self, api_client):
        student, teacher, ca = self._setup_enrolled()
        auth(api_client, student)

        resp = api_client.post(
            '/api/v1/evaluations/',
            {
                'teacher': str(teacher.id),
                'course': str(ca.course.id),
                'term': str(ca.term.id),
                'rating': 6,
            },
            format='json',
        )
        assert resp.status_code == 400

    def test_teacher_can_view_own_evaluations(self, api_client):
        teacher = UserFactory(role='TEACHER')
        TeacherEvaluationFactory(teacher=teacher)
        TeacherEvaluationFactory(teacher=teacher)
        TeacherEvaluationFactory()  # different teacher

        auth(api_client, teacher)
        resp = api_client.get('/api/v1/evaluations/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) == 2

    def test_admin_can_view_all_evaluations(self, api_client):
        TeacherEvaluationFactory()
        TeacherEvaluationFactory()
        admin = UserFactory(role='ADMIN')
        auth(api_client, admin)

        resp = api_client.get('/api/v1/evaluations/')
        assert resp.status_code == 200
        assert len(resp.json()['data']) >= 2

    def test_student_cannot_list_evaluations(self, api_client):
        student = UserFactory(role='STUDENT')
        auth(api_client, student)

        resp = api_client.get('/api/v1/evaluations/')
        assert resp.status_code == 403

    def test_teacher_cannot_submit_evaluation(self, api_client):
        teacher = UserFactory(role='TEACHER')
        other_teacher = UserFactory(role='TEACHER')
        ca = TeacherCourseAssignmentFactory(teacher=other_teacher)
        auth(api_client, teacher)

        resp = api_client.post(
            '/api/v1/evaluations/',
            {
                'teacher': str(other_teacher.id),
                'course': str(ca.course.id),
                'term': str(ca.term.id),
                'rating': 3,
            },
            format='json',
        )
        assert resp.status_code == 403
