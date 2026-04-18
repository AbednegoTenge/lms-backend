"""
Unit tests for Phase 9 — Reports.

Covers:
  - Academic performance: avg_score and pass_rate computed correctly
  - Fee collection: total_expected matches sum of StudentFee.total_amount
  - Teacher evaluation: avg_rating correct
  - Export task: produces presigned URL on success (S3 mocked)
  - Export task failure: status=FAILED, error_message set
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.reports.models import ReportTask
from apps.reports.tasks import export_report_csv
from apps.reports.views import _academic_performance_data, _fee_collection_data, _teacher_evaluation_data
from tests.factories import (
    ReportTaskFactory,
    StudentFeeFactory,
    TeacherCourseAssignmentFactory,
    TermFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Academic performance
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAcademicPerformanceData:

    def _make_graded_attempt(self, quiz, student, score):
        from apps.assessments.models import QuizAttempt
        return QuizAttempt.objects.create(
            quiz=quiz,
            student=student,
            attempt_number=1,
            score=score,
            status=QuizAttempt.GRADED,
        )

    def test_avg_score_and_pass_rate_quiz_only(self):
        from tests.factories import QuizFactory
        quiz = QuizFactory(total_marks=Decimal('10'))
        student1 = UserFactory(role='STUDENT')
        student2 = UserFactory(role='STUDENT')
        # student1: 8/10 = 80% (pass), student2: 4/10 = 40% (fail)
        self._make_graded_attempt(quiz, student1, Decimal('8'))
        self._make_graded_attempt(quiz, student2, Decimal('4'))

        data = _academic_performance_data({})
        assert data['total_students'] == 2
        assert data['avg_score'] == 60.0  # (80+40)/2
        assert data['pass_rate'] == 0.5   # 1/2

    def test_avg_score_all_pass(self):
        from tests.factories import QuizFactory
        quiz = QuizFactory(total_marks=Decimal('10'))
        for score in [6, 7, 8]:
            self._make_graded_attempt(quiz, UserFactory(role='STUDENT'), Decimal(str(score)))

        data = _academic_performance_data({})
        assert data['pass_rate'] == 1.0
        assert data['avg_score'] == pytest.approx(70.0, abs=0.01)

    def test_no_data_returns_zeros(self):
        data = _academic_performance_data({})
        assert data['total_students'] == 0
        assert data['avg_score'] == 0.0
        assert data['pass_rate'] == 0.0

    def test_course_breakdown_present(self):
        from tests.factories import CourseFactory, QuizFactory, TeacherCourseAssignmentFactory
        assignment = TeacherCourseAssignmentFactory()
        quiz = QuizFactory(assignment=assignment, total_marks=Decimal('10'))
        self._make_graded_attempt(quiz, UserFactory(role='STUDENT'), Decimal('8'))

        data = _academic_performance_data({})
        assert len(data['course_breakdown']) == 1
        assert data['course_breakdown'][0]['avg_score'] == 80.0

    def test_ungraded_attempts_excluded(self):
        from apps.assessments.models import QuizAttempt
        from tests.factories import QuizFactory
        quiz = QuizFactory(total_marks=Decimal('10'))
        student = UserFactory(role='STUDENT')
        QuizAttempt.objects.create(
            quiz=quiz, student=student, attempt_number=1, status=QuizAttempt.IN_PROGRESS
        )
        data = _academic_performance_data({})
        assert data['total_students'] == 0


# ---------------------------------------------------------------------------
# Fee collection
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeCollectionData:

    def test_total_expected_matches_sum(self):
        term = TermFactory()
        StudentFeeFactory(term=term, total_amount=Decimal('500'), amount_paid=Decimal('0'))
        StudentFeeFactory(term=term, total_amount=Decimal('300'), amount_paid=Decimal('100'))

        data = _fee_collection_data({'term': str(term.pk)})
        assert data['total_expected'] == '800.00'
        assert data['total_collected'] == '100.00'
        assert data['outstanding'] == '700.00'

    def test_breakdown_by_status(self):
        from apps.fees.models import StudentFee
        term = TermFactory()
        StudentFeeFactory(term=term, total_amount=Decimal('500'), amount_paid=Decimal('0'),
                          payment_status=StudentFee.NOT_PAID)
        StudentFeeFactory(term=term, total_amount=Decimal('300'), amount_paid=Decimal('300'),
                          payment_status=StudentFee.FULLY_PAID)

        data = _fee_collection_data({'term': str(term.pk)})
        statuses = data['breakdown_by_status']
        assert StudentFee.NOT_PAID in statuses
        assert StudentFee.FULLY_PAID in statuses
        assert statuses[StudentFee.NOT_PAID]['count'] == 1
        assert statuses[StudentFee.FULLY_PAID]['count'] == 1

    def test_no_data_returns_zeros(self):
        data = _fee_collection_data({})
        assert data['total_expected'] == '0.00'
        assert data['total_collected'] == '0.00'
        assert data['outstanding'] == '0.00'


# ---------------------------------------------------------------------------
# Teacher evaluations
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherEvaluationData:

    def test_avg_rating_correct(self):
        from tests.factories import CourseFactory, TeacherEvaluationFactory
        teacher = UserFactory(role='TEACHER')
        course = CourseFactory()
        term = TermFactory()
        for rating in [3, 5, 4]:
            TeacherEvaluationFactory(teacher=teacher, course=course, term=term, rating=rating)

        data = _teacher_evaluation_data({})
        assert len(data['by_teacher']) == 1
        assert data['by_teacher'][0]['avg_rating'] == pytest.approx(4.0, abs=0.01)
        assert data['by_teacher'][0]['total_evaluations'] == 3

    def test_no_data_returns_empty_lists(self):
        data = _teacher_evaluation_data({})
        assert data['by_teacher'] == []
        assert data['course_breakdown'] == []


# ---------------------------------------------------------------------------
# Export task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestExportReportCsvTask:

    def test_success_sets_done_and_url(self):
        task = ReportTaskFactory(report_type=ReportTask.FEE_COLLECTION)
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://s3.example.com/report.csv'

        with patch('apps.reports.tasks.boto3.client', return_value=mock_s3):
            export_report_csv(str(task.pk))

        task.refresh_from_db()
        assert task.status == ReportTask.DONE
        assert task.download_url == 'https://s3.example.com/report.csv'
        assert task.completed_at is not None
        mock_s3.put_object.assert_called_once()
        mock_s3.generate_presigned_url.assert_called_once()

    def test_failure_sets_failed_and_error_message(self):
        task = ReportTaskFactory(report_type=ReportTask.ACADEMIC_PERFORMANCE)

        with patch('apps.reports.tasks.boto3.client', side_effect=Exception('S3 unavailable')):
            export_report_csv(str(task.pk))

        task.refresh_from_db()
        assert task.status == ReportTask.FAILED
        assert 'S3 unavailable' in task.error_message

    def test_nonexistent_task_returns_gracefully(self):
        import uuid
        export_report_csv(str(uuid.uuid4()))  # should not raise
