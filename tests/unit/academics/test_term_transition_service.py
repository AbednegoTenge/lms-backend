"""
Unit tests for TermTransitionService.

Celery tasks are mocked so these run without a Celery broker.
on_commit callbacks are not fired inside @pytest.mark.django_db transactions,
so we assert on mock.delay calls directly.
"""
import datetime
from unittest.mock import patch, MagicMock

import pytest

from apps.academics.models import AcademicYear, Level, Term
from apps.academics.services import TermTransitionService, TransitionError
from apps.enrollment.models import StudentProfile
from tests.factories import (
    AcademicYearFactory,
    LevelFactory,
    StudentProfileFactory,
    TermFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_year_with_terms(is_current_term=None, start_year=2024):
    """Create an AcademicYear with 3 Terms. is_current_term is the term_number to mark current."""
    year = AcademicYearFactory(
        start_date=datetime.date(start_year, 9, 1),
        end_date=datetime.date(start_year + 1, 7, 31),
    )
    t1 = TermFactory(academic_year=year, term_number=1, is_current=(is_current_term == 1))
    t2 = TermFactory(academic_year=year, term_number=2, is_current=(is_current_term == 2))
    t3 = TermFactory(academic_year=year, term_number=3, is_current=(is_current_term == 3))
    return year, t1, t2, t3


def make_student(level_number=1, status=StudentProfile.ACTIVE):
    level = LevelFactory(number=level_number)
    user = UserFactory(role='STUDENT')
    profile = StudentProfileFactory(user=user, level=level, status=status)
    return profile


# ---------------------------------------------------------------------------
# Rule 1: term_number < 3
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRule1AdvanceWithinYear:
    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_term1_advances_to_term2(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=1)

        result = TermTransitionService.transition()

        t1.refresh_from_db()
        t2.refresh_from_db()
        assert t1.is_current is False
        assert t2.is_current is True
        assert result['new_term'] == str(t2.id)
        assert result['promoted'] == 0
        assert result['graduated'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_term2_advances_to_term3(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=2)

        result = TermTransitionService.transition()

        t2.refresh_from_db()
        t3.refresh_from_db()
        assert t2.is_current is False
        assert t3.is_current is True
        assert result['new_term'] == str(t3.id)
        assert result['promoted'] == 0
        assert result['graduated'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_students_not_changed_on_rule1(self, mock_overdue, mock_generate):
        make_year_with_terms(is_current_term=1)
        student = make_student(level_number=1)

        TermTransitionService.transition()

        student.refresh_from_db()
        assert student.level.number == 1
        assert student.status == StudentProfile.ACTIVE

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_missing_next_term_raises_error(self, mock_overdue, mock_generate):
        # Create year with only term 1 (no term 2)
        year = AcademicYearFactory()
        TermFactory(academic_year=year, term_number=1, is_current=True)

        with pytest.raises(TransitionError, match='Term 2 not found'):
            TermTransitionService.transition()


# ---------------------------------------------------------------------------
# Rule 2: term_number == 3, level < 3 → promote
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRule2PromoteStudents:
    def _setup_next_year(self, current_year):
        next_year = AcademicYearFactory(
            start_date=current_year.end_date + datetime.timedelta(days=1),
            end_date=current_year.end_date + datetime.timedelta(days=365),
        )
        TermFactory(academic_year=next_year, term_number=1, is_current=False)
        return next_year

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_level1_student_promoted_to_level2(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        student = make_student(level_number=1)

        result = TermTransitionService.transition()

        student.refresh_from_db()
        assert student.level.number == 2
        assert student.status == StudentProfile.ACTIVE
        assert result['promoted'] == 1
        assert result['graduated'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_level2_student_promoted_to_level3(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        student = make_student(level_number=2)

        result = TermTransitionService.transition()

        student.refresh_from_db()
        assert student.level.number == 3
        assert student.status == StudentProfile.ACTIVE
        assert result['promoted'] == 1
        assert result['graduated'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_multiple_students_promoted(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        make_student(level_number=1)
        make_student(level_number=1)
        make_student(level_number=2)

        result = TermTransitionService.transition()

        assert result['promoted'] == 3
        assert result['graduated'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_term_advances_to_next_year_term1(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        next_year = self._setup_next_year(year)
        next_t1 = Term.objects.get(academic_year=next_year, term_number=1)

        result = TermTransitionService.transition()

        t3.refresh_from_db()
        next_t1.refresh_from_db()
        assert t3.is_current is False
        assert next_t1.is_current is True
        assert result['new_term'] == str(next_t1.id)

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_inactive_students_not_promoted(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        make_student(level_number=1, status=StudentProfile.INACTIVE)
        make_student(level_number=1, status=StudentProfile.SUSPENDED)

        result = TermTransitionService.transition()

        assert result['promoted'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_no_next_academic_year_raises_error(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        # No next year created

        with pytest.raises(TransitionError, match='Next academic year not found'):
            TermTransitionService.transition()

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_no_term1_in_next_year_raises_error(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        next_year = AcademicYearFactory(
            start_date=year.end_date + datetime.timedelta(days=1),
            end_date=year.end_date + datetime.timedelta(days=365),
        )
        # Only term 2 in next year — term 1 missing
        TermFactory(academic_year=next_year, term_number=2, is_current=False)

        with pytest.raises(TransitionError, match='Term 1 not found'):
            TermTransitionService.transition()


# ---------------------------------------------------------------------------
# Rule 3: term_number == 3, level == 3 → graduate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRule3GraduateStudents:
    def _setup_next_year(self, current_year):
        next_year = AcademicYearFactory(
            start_date=current_year.end_date + datetime.timedelta(days=1),
            end_date=current_year.end_date + datetime.timedelta(days=365),
        )
        TermFactory(academic_year=next_year, term_number=1, is_current=False)
        return next_year

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_level3_student_graduated(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        student = make_student(level_number=3)

        result = TermTransitionService.transition()

        student.refresh_from_db()
        assert student.status == StudentProfile.GRADUATED
        assert result['graduated'] == 1
        assert result['promoted'] == 0

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_multiple_students_graduated(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        make_student(level_number=3)
        make_student(level_number=3)
        make_student(level_number=3)

        result = TermTransitionService.transition()

        assert result['graduated'] == 3

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_mixed_levels_promoted_and_graduated(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        self._setup_next_year(year)
        make_student(level_number=1)
        make_student(level_number=2)
        make_student(level_number=3)
        make_student(level_number=3)

        result = TermTransitionService.transition()

        assert result['promoted'] == 2
        assert result['graduated'] == 2


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTransitionErrors:
    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_no_current_term_raises_error(self, mock_overdue, mock_generate):
        # No terms marked as current
        AcademicYearFactory()

        with pytest.raises(TransitionError, match='No current term found'):
            TermTransitionService.transition()


# ---------------------------------------------------------------------------
# Atomicity: verify DB state on error is rolled back
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTransitionAtomicity:
    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_term_not_changed_when_next_term_missing(self, mock_overdue, mock_generate):
        # Term 1 current, but no term 2 → should roll back
        year = AcademicYearFactory()
        t1 = TermFactory(academic_year=year, term_number=1, is_current=True)

        with pytest.raises(TransitionError):
            TermTransitionService.transition()

        t1.refresh_from_db()
        assert t1.is_current is True  # unchanged due to rollback
