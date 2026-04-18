"""
Integration tests for Phase 6 — Term Transition.

Covers:
  - POST /api/v1/terms/transition/ permissions and response
  - GRADUATED guard in enrollment endpoints
  - mark_overdue_fees Celery task
  - generate_term_fees Celery task
  - FeeCalculationService.calculate_for_student
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academics.models import Level, Term
from apps.enrollment.models import StudentProfile
from apps.fees.models import StudentFee
from apps.fees.services import FeeCalculationService
from apps.fees.tasks import generate_term_fees, mark_overdue_fees
from tests.factories import (
    AcademicYearFactory,
    AdditionalFeeFactory,
    FeeStructureFactory,
    LevelFactory,
    StudentFeeFactory,
    StudentProfileFactory,
    TermFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


TRANSITION_URL = '/api/v1/terms/transition/'


def make_year_with_terms(is_current_term=None, start_year=2024):
    year = AcademicYearFactory(
        start_date=datetime.date(start_year, 9, 1),
        end_date=datetime.date(start_year + 1, 7, 31),
    )
    t1 = TermFactory(academic_year=year, term_number=1, is_current=(is_current_term == 1))
    t2 = TermFactory(academic_year=year, term_number=2, is_current=(is_current_term == 2))
    t3 = TermFactory(academic_year=year, term_number=3, is_current=(is_current_term == 3))
    return year, t1, t2, t3


def setup_next_year(current_year):
    next_year = AcademicYearFactory(
        start_date=current_year.end_date + datetime.timedelta(days=1),
        end_date=current_year.end_date + datetime.timedelta(days=365),
    )
    next_t1 = TermFactory(academic_year=next_year, term_number=1, is_current=False)
    return next_year, next_t1


# ---------------------------------------------------------------------------
# Transition endpoint — permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTransitionPermissions:
    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_admin_can_transition(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=1)
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_200_OK
        assert res.data['success'] is True
        assert 'new_term' in res.data['data']

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_super_admin_can_transition(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=1)
        super_admin = UserFactory(role='SUPER_ADMIN')
        client = auth_client(super_admin)

        res = client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_200_OK

    def test_student_cannot_transition(self):
        student = UserFactory(role='STUDENT')
        client = auth_client(student)

        res = client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_transition(self):
        teacher = UserFactory(role='TEACHER')
        client = auth_client(teacher)

        res = client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_principal_cannot_transition(self):
        principal = UserFactory(role='PRINCIPAL')
        client = auth_client(principal)

        res = client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_transition(self, api_client):
        res = api_client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Transition endpoint — response shape and correctness
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTransitionResponse:
    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_rule1_response(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=1)
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.post(TRANSITION_URL)

        data = res.data['data']
        assert data['promoted'] == 0
        assert data['graduated'] == 0
        assert data['new_term'] == str(t2.id)

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_rule3_response_graduates_and_promotes(self, mock_overdue, mock_generate):
        year, t1, t2, t3 = make_year_with_terms(is_current_term=3)
        setup_next_year(year)

        level1 = LevelFactory(number=1)
        level3 = LevelFactory(number=3)
        s1_user = UserFactory(role='STUDENT')
        s1 = StudentProfileFactory(user=s1_user, level=level1, status=StudentProfile.ACTIVE)
        s2_user = UserFactory(role='STUDENT')
        s2 = StudentProfileFactory(user=s2_user, level=level3, status=StudentProfile.ACTIVE)

        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.post(TRANSITION_URL)

        data = res.data['data']
        assert data['promoted'] == 1
        assert data['graduated'] == 1

    @patch('apps.fees.tasks.generate_term_fees')
    @patch('apps.fees.tasks.mark_overdue_fees')
    def test_no_current_term_returns_400(self, mock_overdue, mock_generate):
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.post(TRANSITION_URL)

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.data['success'] is False


# ---------------------------------------------------------------------------
# GRADUATED guard — enrollment endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGraduatedGuard:
    def _make_graduated_student(self):
        level = LevelFactory(number=1)
        user = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=user, level=level, status=StudentProfile.GRADUATED)
        return profile

    def test_partial_update_blocked_for_graduated(self):
        profile = self._make_graduated_student()
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.patch(
            f'/api/v1/students/{profile.pk}/',
            {'class_section': '1A'},
            format='json',
        )

        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert 'graduated' in res.data['message'].lower()

    def test_assign_program_blocked_for_graduated(self):
        from apps.academics.models import Program
        profile = self._make_graduated_student()
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        program = Program.objects.first()

        res = client.post(
            f'/api/v1/students/{profile.pk}/assign-program/',
            {'program_id': str(program.pk)},
            format='json',
        )

        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_enroll_electives_blocked_for_graduated(self):
        profile = self._make_graduated_student()
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.post(
            f'/api/v1/students/{profile.pk}/enroll-electives/',
            {'course_ids': []},
            format='json',
        )

        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_active_student_not_blocked(self):
        level = LevelFactory(number=1)
        user = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=user, level=level, status=StudentProfile.ACTIVE)
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)

        res = client.patch(
            f'/api/v1/students/{profile.pk}/',
            {'class_section': '1A'},
            format='json',
        )

        # Should not be blocked by GRADUATED guard (may fail for other reasons, but not 403-graduated)
        assert res.status_code != status.HTTP_403_FORBIDDEN or 'graduated' not in res.data.get('message', '').lower()


# ---------------------------------------------------------------------------
# mark_overdue_fees Celery task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMarkOverdueFees:
    def test_not_paid_becomes_overdue(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student,
            term=term,
            payment_status=StudentFee.NOT_PAID,
        )

        mark_overdue_fees(str(term.id))

        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.OVERDUE

    def test_partially_paid_becomes_overdue(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student,
            term=term,
            amount_paid=Decimal('100.00'),
            payment_status=StudentFee.PARTIALLY_PAID,
        )

        mark_overdue_fees(str(term.id))

        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.OVERDUE

    def test_fully_paid_not_affected(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student,
            term=term,
            amount_paid=Decimal('500.00'),
            payment_status=StudentFee.FULLY_PAID,
        )

        mark_overdue_fees(str(term.id))

        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.FULLY_PAID

    def test_already_overdue_stays_overdue(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student,
            term=term,
            payment_status=StudentFee.OVERDUE,
        )

        result = mark_overdue_fees(str(term.id))

        # OVERDUE is excluded from the filter so count should be 0
        assert result == 0

    def test_only_affects_given_term(self):
        term1 = TermFactory()
        term2 = TermFactory()
        student = UserFactory(role='STUDENT')
        fee1 = StudentFeeFactory(student=student, term=term1, payment_status=StudentFee.NOT_PAID)
        fee2 = StudentFeeFactory(student=student, term=term2, payment_status=StudentFee.NOT_PAID)

        mark_overdue_fees(str(term1.id))

        fee1.refresh_from_db()
        fee2.refresh_from_db()
        assert fee1.payment_status == StudentFee.OVERDUE
        assert fee2.payment_status == StudentFee.NOT_PAID

    def test_returns_count_of_updated_fees(self):
        term = TermFactory()
        for _ in range(3):
            s = UserFactory(role='STUDENT')
            StudentFeeFactory(student=s, term=term, payment_status=StudentFee.NOT_PAID)

        result = mark_overdue_fees(str(term.id))

        assert result == 3


# ---------------------------------------------------------------------------
# generate_term_fees Celery task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateTermFees:
    def test_generates_fees_for_active_students(self):
        level = LevelFactory(number=1)
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('500.00'))

        user = UserFactory(role='STUDENT')
        StudentProfileFactory(user=user, level=level, status=StudentProfile.ACTIVE)

        result = generate_term_fees()

        assert result == 1
        assert StudentFee.objects.filter(student=user, term=term).exists()

    def test_no_current_term_returns_zero(self):
        result = generate_term_fees()
        assert result == 0

    def test_graduated_students_not_included(self):
        level = LevelFactory(number=1)
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('500.00'))

        user = UserFactory(role='STUDENT')
        StudentProfileFactory(user=user, level=level, status=StudentProfile.GRADUATED)

        result = generate_term_fees()

        assert result == 0

    def test_idempotent_does_not_duplicate(self):
        level = LevelFactory(number=1)
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('500.00'))

        user = UserFactory(role='STUDENT')
        StudentProfileFactory(user=user, level=level, status=StudentProfile.ACTIVE)

        generate_term_fees()
        generate_term_fees()

        assert StudentFee.objects.filter(student=user, term=term).count() == 1


# ---------------------------------------------------------------------------
# FeeCalculationService
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeCalculationService:
    def test_creates_student_fee_with_correct_amounts(self):
        level = LevelFactory(number=1)
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('400.00'))
        AdditionalFeeFactory(
            term=term,
            amount=Decimal('50.00'),
            applies_to='ALL',
        )

        user = UserFactory(role='STUDENT')
        StudentProfileFactory(user=user, level=level, status=StudentProfile.ACTIVE)

        result = FeeCalculationService.calculate_for_student(user, term)

        assert result is not None
        assert result.base_amount == Decimal('400.00')
        assert result.additional_amount == Decimal('50.00')
        assert result.total_amount == Decimal('450.00')
        assert result.payment_status == StudentFee.NOT_PAID

    def test_no_fee_structure_returns_none(self):
        level = LevelFactory(number=2)
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        # No FeeStructure created

        user = UserFactory(role='STUDENT')
        StudentProfileFactory(user=user, level=level, status=StudentProfile.ACTIVE)

        result = FeeCalculationService.calculate_for_student(user, term)

        assert result is None

    def test_idempotent_returns_existing_fee(self):
        level = LevelFactory(number=1)
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('300.00'))

        user = UserFactory(role='STUDENT')
        StudentProfileFactory(user=user, level=level, status=StudentProfile.ACTIVE)

        fee1 = FeeCalculationService.calculate_for_student(user, term)
        fee2 = FeeCalculationService.calculate_for_student(user, term)

        assert fee1.pk == fee2.pk
        assert StudentFee.objects.filter(student=user, term=term).count() == 1

    def test_no_student_profile_returns_none(self):
        year = AcademicYearFactory()
        term = TermFactory(academic_year=year, term_number=1, is_current=True)
        user = UserFactory(role='TEACHER')  # no StudentProfile

        result = FeeCalculationService.calculate_for_student(user, term)

        assert result is None


# ---------------------------------------------------------------------------
# StudentFee.save() — payment_status recomputation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentFeePaymentStatus:
    def test_zero_paid_is_not_paid(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student, term=term,
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )
        assert fee.payment_status == StudentFee.NOT_PAID

    def test_partial_payment_is_partially_paid(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student, term=term,
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('200.00'),
        )
        fee.save()
        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.PARTIALLY_PAID

    def test_full_payment_is_fully_paid(self):
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student, term=term,
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('500.00'),
        )
        fee.save()
        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.FULLY_PAID

    def test_overdue_status_preserved_on_save(self):
        """OVERDUE can be set externally and is preserved through save()."""
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(
            student=student, term=term,
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
            payment_status=StudentFee.OVERDUE,
        )
        fee.save()
        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.OVERDUE
