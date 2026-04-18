"""
Integration tests for Phase 9 — Reports.

Covers:
  - Admin/Principal can access report endpoints
  - Student cannot access → 403
  - Teacher cannot access → 403
  - Academic performance returns correct structure
  - Fee collection: total_expected correct
  - Teacher evaluations: avg_rating correct
  - POST /reports/export/ creates ReportTask and returns task_id
  - GET /reports/export/{task_id}/ returns task status (DONE with download_url)
  - GET /reports/export/{task_id}/ → 403 for another user's task
  - Export task failure: status=FAILED, error_message set
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.fees.models import StudentFee
from apps.reports.models import ReportTask
from tests.factories import (
    ReportTaskFactory,
    StudentFeeFactory,
    TermFactory,
    UserFactory,
)


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


ACADEMIC_URL = '/api/v1/reports/academic-performance/'
FEE_URL = '/api/v1/reports/fee-collection/'
EVAL_URL = '/api/v1/reports/teacher-evaluations/'
EXPORT_URL = '/api/v1/reports/export/'


def export_status_url(pk):
    return f'/api/v1/reports/export/{pk}/'


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReportPermissions:

    def test_student_cannot_access_academic_performance(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).get(ACADEMIC_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_access_academic_performance(self):
        teacher = UserFactory(role='TEACHER')
        resp = auth_client(teacher).get(ACADEMIC_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_access_fee_collection(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).get(FEE_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_access_teacher_evaluations(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).get(EVAL_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_export(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).post(EXPORT_URL, {
            'report_type': ReportTask.ACADEMIC_PERFORMANCE, 'format': ReportTask.CSV
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_access_academic_performance(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).get(ACADEMIC_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_principal_can_access_fee_collection(self):
        principal = UserFactory(role='PRINCIPAL')
        resp = auth_client(principal).get(FEE_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated_cannot_access(self):
        resp = APIClient().get(ACADEMIC_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Academic performance report
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAcademicPerformanceReport:

    def _make_graded_attempt(self, quiz, student, score):
        from apps.assessments.models import QuizAttempt
        return QuizAttempt.objects.create(
            quiz=quiz, student=student, attempt_number=1,
            score=score, status=QuizAttempt.GRADED,
        )

    def test_returns_correct_structure(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).get(ACADEMIC_URL)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data['data']
        assert 'total_students' in data
        assert 'avg_score' in data
        assert 'pass_rate' in data
        assert 'course_breakdown' in data

    def test_avg_score_correct(self):
        from tests.factories import QuizFactory
        admin = UserFactory(role='ADMIN')
        quiz = QuizFactory(total_marks=Decimal('10'))
        student = UserFactory(role='STUDENT')
        self._make_graded_attempt(quiz, student, Decimal('8'))

        resp = auth_client(admin).get(ACADEMIC_URL)
        data = resp.data['data']
        assert data['avg_score'] == 80.0
        assert data['total_students'] == 1


# ---------------------------------------------------------------------------
# Fee collection report
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeCollectionReport:

    def test_total_expected_matches_sum(self):
        admin = UserFactory(role='ADMIN')
        term = TermFactory()
        StudentFeeFactory(term=term, total_amount=Decimal('500'), amount_paid=Decimal('0'),
                          payment_status=StudentFee.NOT_PAID)
        StudentFeeFactory(term=term, total_amount=Decimal('300'), amount_paid=Decimal('200'),
                          payment_status=StudentFee.PARTIALLY_PAID)

        resp = auth_client(admin).get(FEE_URL, {'term': str(term.pk)})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data['data']
        assert data['total_expected'] == '800.00'
        assert data['total_collected'] == '200.00'
        assert data['outstanding'] == '600.00'

    def test_breakdown_by_status_correct(self):
        admin = UserFactory(role='ADMIN')
        term = TermFactory()
        StudentFeeFactory(term=term, total_amount=Decimal('500'), amount_paid=Decimal('0'),
                          payment_status=StudentFee.NOT_PAID)

        resp = auth_client(admin).get(FEE_URL, {'term': str(term.pk)})
        assert StudentFee.NOT_PAID in resp.data['data']['breakdown_by_status']


# ---------------------------------------------------------------------------
# Teacher evaluations report
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherEvaluationsReport:

    def test_avg_rating_correct(self):
        from tests.factories import CourseFactory, TeacherEvaluationFactory
        admin = UserFactory(role='ADMIN')
        teacher = UserFactory(role='TEACHER')
        course = CourseFactory()
        term = TermFactory()
        for rating in [4, 5]:
            TeacherEvaluationFactory(teacher=teacher, course=course, term=term, rating=rating)

        resp = auth_client(admin).get(EVAL_URL, {'teacher': str(teacher.pk)})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data['data']
        assert len(data['by_teacher']) == 1
        assert data['by_teacher'][0]['avg_rating'] == pytest.approx(4.5, abs=0.01)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReportExport:

    def _mock_s3(self, presigned_url='https://s3.example.com/report.csv'):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = presigned_url
        return mock_s3

    def test_export_creates_task_and_returns_task_id(self):
        admin = UserFactory(role='ADMIN')
        with patch('apps.reports.tasks.boto3.client', return_value=self._mock_s3()):
            resp = auth_client(admin).post(EXPORT_URL, {
                'report_type': ReportTask.FEE_COLLECTION,
                'format': ReportTask.CSV,
            })
        assert resp.status_code == status.HTTP_202_ACCEPTED
        task_id = resp.data['data']['task_id']
        assert ReportTask.objects.filter(pk=task_id, requested_by=admin).exists()

    def test_export_task_done_with_download_url(self):
        admin = UserFactory(role='ADMIN')
        with patch('apps.reports.tasks.boto3.client', return_value=self._mock_s3()):
            resp = auth_client(admin).post(EXPORT_URL, {
                'report_type': ReportTask.FEE_COLLECTION,
                'format': ReportTask.CSV,
            })
        task_id = resp.data['data']['task_id']
        task = ReportTask.objects.get(pk=task_id)
        assert task.status == ReportTask.DONE
        assert task.download_url == 'https://s3.example.com/report.csv'

    def test_export_task_failure_sets_failed_status(self):
        admin = UserFactory(role='ADMIN')
        with patch('apps.reports.tasks.boto3.client', side_effect=Exception('S3 down')):
            resp = auth_client(admin).post(EXPORT_URL, {
                'report_type': ReportTask.ACADEMIC_PERFORMANCE,
                'format': ReportTask.CSV,
            })
        task_id = resp.data['data']['task_id']
        task = ReportTask.objects.get(pk=task_id)
        assert task.status == ReportTask.FAILED
        assert 'S3 down' in task.error_message

    def test_export_status_returns_task(self):
        admin = UserFactory(role='ADMIN')
        task = ReportTaskFactory(requested_by=admin, status=ReportTask.DONE,
                                 download_url='https://s3.example.com/report.csv')
        resp = auth_client(admin).get(export_status_url(task.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['data']['status'] == ReportTask.DONE
        assert resp.data['data']['download_url'] == 'https://s3.example.com/report.csv'

    def test_user_cannot_poll_another_users_task(self):
        admin = UserFactory(role='ADMIN')
        other_admin = UserFactory(role='ADMIN')
        task = ReportTaskFactory(requested_by=admin)
        resp = auth_client(other_admin).get(export_status_url(task.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_export_status_404_for_nonexistent_task(self):
        import uuid
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).get(export_status_url(uuid.uuid4()))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_invalid_report_type_returns_400(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(EXPORT_URL, {
            'report_type': 'INVALID',
            'format': ReportTask.CSV,
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
