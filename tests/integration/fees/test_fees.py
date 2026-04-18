"""
Integration tests for Phase 7 — Fee Management.

Covers:
  - FeeStructure CRUD permissions and response
  - StudentFee list/retrieve permissions
  - Payment recording → amount_paid updated → status transitions
  - OVERDUE status preserved across payments
  - send_fee_reminder enqueues Celery task
  - GET /api/v1/students/{id}/fees/ (student can only see own)
  - FeeCalculationService idempotency
  - Cache invalidation on FeeStructure update
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.fees.models import Payment, StudentFee
from apps.fees.tasks import send_fee_reminder
from tests.factories import (
    AdditionalFeeFactory,
    FeeStructureFactory,
    LevelFactory,
    PaymentFactory,
    ProgramFactory,
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


FEE_STRUCTURE_LIST = '/api/v1/fee-structures/'
STUDENT_FEE_LIST = '/api/v1/student-fees/'
STUDENT_FEE_REMINDER = '/api/v1/student-fees/send-reminder/'


def student_fee_url(pk):
    return f'/api/v1/student-fees/{pk}/'


def student_fee_payments_url(pk):
    return f'/api/v1/student-fees/{pk}/payments/'


def student_fees_action_url(student_pk):
    return f'/api/v1/students/{student_pk}/fees/'


# ---------------------------------------------------------------------------
# FeeStructure CRUD
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeStructureCRUD:
    def test_admin_can_create_fee_structure(self):
        admin = UserFactory(role='ADMIN')
        level = LevelFactory(number=1)

        data = {
            'level': str(level.pk),
            'base_amount': '500.00',
            'description': 'Standard fee',
            'effective_from': '2024-01-01',
        }
        resp = auth_client(admin).post(FEE_STRUCTURE_LIST, data, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['data']['base_amount'] == '500.00'

    def test_principal_cannot_create_fee_structure(self):
        principal = UserFactory(role='PRINCIPAL')
        level = LevelFactory(number=1)

        data = {
            'level': str(level.pk),
            'base_amount': '500.00',
            'description': 'Fee',
            'effective_from': '2024-01-01',
        }
        resp = auth_client(principal).post(FEE_STRUCTURE_LIST, data, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_principal_can_list_fee_structures(self):
        principal = UserFactory(role='PRINCIPAL')
        level = LevelFactory(number=1)
        FeeStructureFactory(level=level)

        resp = auth_client(principal).get(FEE_STRUCTURE_LIST)
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_update_fee_structure(self):
        admin = UserFactory(role='ADMIN')
        level = LevelFactory(number=1)
        structure = FeeStructureFactory(level=level, base_amount=Decimal('400.00'))

        resp = auth_client(admin).patch(
            f'{FEE_STRUCTURE_LIST}{structure.pk}/',
            {'base_amount': '600.00'},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['data']['base_amount'] == '600.00'

    def test_admin_can_delete_fee_structure(self):
        admin = UserFactory(role='ADMIN')
        level = LevelFactory(number=1)
        structure = FeeStructureFactory(level=level)

        resp = auth_client(admin).delete(f'{FEE_STRUCTURE_LIST}{structure.pk}/')
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_student_cannot_list_fee_structures(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).get(FEE_STRUCTURE_LIST)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_fee_structure_list_filter_by_level(self):
        admin = UserFactory(role='ADMIN')
        level1 = LevelFactory(number=1)
        level2 = LevelFactory(number=2)
        FeeStructureFactory(level=level1)
        FeeStructureFactory(level=level2)

        resp = auth_client(admin).get(f'{FEE_STRUCTURE_LIST}?level={level1.pk}')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data['data']
        assert len(results) == 1


# ---------------------------------------------------------------------------
# StudentFee list / retrieve
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentFeeListRetrieve:
    def test_admin_can_list_all_student_fees(self):
        admin = UserFactory(role='ADMIN')
        term = TermFactory()
        StudentFeeFactory(term=term)
        StudentFeeFactory(term=term)

        resp = auth_client(admin).get(STUDENT_FEE_LIST)
        assert resp.status_code == status.HTTP_200_OK

    def test_principal_can_list_all_student_fees(self):
        principal = UserFactory(role='PRINCIPAL')
        StudentFeeFactory()

        resp = auth_client(principal).get(STUDENT_FEE_LIST)
        assert resp.status_code == status.HTTP_200_OK

    def test_student_cannot_list_all_fees(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).get(STUDENT_FEE_LIST)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_retrieve_any_student_fee(self):
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory()

        resp = auth_client(admin).get(student_fee_url(fee.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['data']['id'] == str(fee.pk)

    def test_student_can_retrieve_own_fee(self):
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(student=student)

        resp = auth_client(student).get(student_fee_url(fee.pk))
        assert resp.status_code == status.HTTP_200_OK

    def test_student_cannot_retrieve_another_students_fee(self):
        student = UserFactory(role='STUDENT')
        other = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(student=other)

        resp = auth_client(student).get(student_fee_url(fee.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_fee_filter_by_status(self):
        admin = UserFactory(role='ADMIN')
        term = TermFactory()
        overdue_fee = StudentFeeFactory(term=term)
        StudentFee.objects.filter(pk=overdue_fee.pk).update(payment_status=StudentFee.OVERDUE)
        StudentFeeFactory(term=term)  # NOT_PAID

        resp = auth_client(admin).get(f'{STUDENT_FEE_LIST}?status=OVERDUE')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data['data']
        assert len(results) >= 1
        assert all(r['payment_status'] == StudentFee.OVERDUE for r in results)

    def test_student_fee_filter_by_term(self):
        admin = UserFactory(role='ADMIN')
        term1 = TermFactory()
        term2 = TermFactory()
        StudentFeeFactory(term=term1)
        StudentFeeFactory(term=term2)

        resp = auth_client(admin).get(f'{STUDENT_FEE_LIST}?term={term1.pk}')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data['data']
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Payment recording and status transitions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPaymentRecording:
    def test_admin_records_partial_payment_sets_partially_paid(self):
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )

        data = {
            'amount': '200.00',
            'payment_method': 'CASH',
            'paid_at': '2024-09-01T10:00:00Z',
        }
        resp = auth_client(admin).post(student_fee_payments_url(fee.pk), data, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['data']['new_status'] == StudentFee.PARTIALLY_PAID
        assert resp.data['data']['amount_paid'] == '200.00'

    def test_second_payment_completes_to_fully_paid(self):
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )

        pay_data = lambda amount: {
            'amount': amount,
            'payment_method': 'CASH',
            'paid_at': '2024-09-01T10:00:00Z',
        }
        auth_client(admin).post(student_fee_payments_url(fee.pk), pay_data('200.00'), format='json')
        resp = auth_client(admin).post(student_fee_payments_url(fee.pk), pay_data('300.00'), format='json')

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['data']['new_status'] == StudentFee.FULLY_PAID
        assert Decimal(resp.data['data']['amount_paid']) == Decimal('500.00')

    def test_payment_updates_amount_paid_via_signal(self):
        """Verify Payment post_save signal aggregates total paid correctly."""
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory(
            base_amount=Decimal('1000.00'),
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('0.00'),
        )

        PaymentFactory(student_fee=fee, amount=Decimal('300.00'))
        PaymentFactory(student_fee=fee, amount=Decimal('250.00'))

        fee.refresh_from_db()
        assert fee.amount_paid == Decimal('550.00')
        assert fee.payment_status == StudentFee.PARTIALLY_PAID

    def test_overdue_fee_with_payment_stays_overdue(self):
        """OVERDUE status is not overridden when a payment is made."""
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )
        StudentFee.objects.filter(pk=fee.pk).update(payment_status=StudentFee.OVERDUE)

        data = {
            'amount': '200.00',
            'payment_method': 'MOBILE_MONEY',
            'paid_at': '2024-09-01T10:00:00Z',
        }
        resp = auth_client(admin).post(student_fee_payments_url(fee.pk), data, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['data']['new_status'] == StudentFee.OVERDUE

    def test_student_cannot_record_payment(self):
        student = UserFactory(role='STUDENT')
        fee = StudentFeeFactory(student=student)

        data = {
            'amount': '100.00',
            'payment_method': 'CASH',
            'paid_at': '2024-09-01T10:00:00Z',
        }
        resp = auth_client(student).post(student_fee_payments_url(fee.pk), data, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_payment_missing_required_fields_returns_400(self):
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory()

        resp = auth_client(admin).post(student_fee_payments_url(fee.pk), {}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_payment_recorded_by_is_set_to_requesting_admin(self):
        admin = UserFactory(role='ADMIN')
        fee = StudentFeeFactory()

        data = {
            'amount': '100.00',
            'payment_method': 'CASH',
            'paid_at': '2024-09-01T10:00:00Z',
        }
        auth_client(admin).post(student_fee_payments_url(fee.pk), data, format='json')
        payment = Payment.objects.filter(student_fee=fee).first()
        assert payment.recorded_by == admin


# ---------------------------------------------------------------------------
# send_fee_reminder
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSendFeeReminder:
    def test_admin_can_send_reminder(self):
        admin = UserFactory(role='ADMIN')
        s1 = UserFactory(role='STUDENT')
        s2 = UserFactory(role='STUDENT')

        with patch('apps.fees.views.send_fee_reminder') as mock_task:
            mock_task.delay = mock_task  # make .delay callable
            resp = auth_client(admin).post(
                STUDENT_FEE_REMINDER,
                {'student_ids': [str(s1.pk), str(s2.pk)], 'message': 'Pay your fees!'},
                format='json',
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['data']['queued'] == 2

    def test_reminder_enqueues_with_correct_student_ids(self):
        admin = UserFactory(role='ADMIN')
        student = UserFactory(role='STUDENT')

        with patch('apps.fees.views.send_fee_reminder') as mock_task:
            mock_delay = mock_task.delay
            auth_client(admin).post(
                STUDENT_FEE_REMINDER,
                {'student_ids': [str(student.pk)], 'message': 'Reminder'},
                format='json',
            )
            mock_delay.assert_called_once_with(
                student_ids=[str(student.pk)], message='Reminder'
            )

    def test_student_cannot_send_reminder(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).post(
            STUDENT_FEE_REMINDER,
            {'student_ids': [], 'message': 'x'},
            format='json',
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_missing_student_ids_returns_400(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(
            STUDENT_FEE_REMINDER,
            {'message': 'Pay now'},
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_message_returns_400(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(
            STUDENT_FEE_REMINDER,
            {'student_ids': ['some-id']},
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_send_fee_reminder_task_returns_count(self):
        """Direct task invocation returns count of active students notified."""
        s1 = UserFactory(role='STUDENT')
        s2 = UserFactory(role='STUDENT')

        result = send_fee_reminder(
            student_ids=[str(s1.pk), str(s2.pk)],
            message='Please pay your fees.',
        )
        assert result == 2


# ---------------------------------------------------------------------------
# GET /api/v1/students/{id}/fees/ (StudentViewSet.fees action)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentFeesAction:
    def test_admin_can_view_student_fees(self):
        admin = UserFactory(role='ADMIN')
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student)
        term = TermFactory()
        StudentFeeFactory(student=student, term=term)

        resp = auth_client(admin).get(student_fees_action_url(profile.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data['data']) == 1

    def test_student_can_view_own_fees(self):
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student)
        term = TermFactory()
        StudentFeeFactory(student=student, term=term)

        resp = auth_client(student).get(student_fees_action_url(profile.pk))
        assert resp.status_code == status.HTTP_200_OK

    def test_student_cannot_view_another_students_fees(self):
        student = UserFactory(role='STUDENT')
        other = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=other)

        resp = auth_client(student).get(student_fees_action_url(profile.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_view_student_fees_action(self):
        teacher = UserFactory(role='TEACHER')
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student)

        resp = auth_client(teacher).get(student_fees_action_url(profile.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# FeeStructure cache invalidation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeStructureCacheInvalidation:
    def setup_method(self):
        from django.core.cache import cache
        cache.clear()

    def test_cache_invalidated_on_fee_structure_update_via_api(self):
        from django.core.cache import cache
        from apps.fees.services import FeeCalculationService, _fee_structure_cache_key

        admin = UserFactory(role='ADMIN')
        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        structure = FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('400.00'))

        # Populate cache
        FeeCalculationService.calculate_for_student(student, term)
        key = _fee_structure_cache_key(level.pk, None)
        assert cache.get(key) is not None

        # Update via API → signal fires → cache cleared
        auth_client(admin).patch(
            f'{FEE_STRUCTURE_LIST}{structure.pk}/',
            {'base_amount': '800.00'},
            format='json',
        )
        assert cache.get(key) is None

    def test_cache_invalidated_on_fee_structure_delete_via_api(self):
        from django.core.cache import cache
        from apps.fees.services import FeeCalculationService, _fee_structure_cache_key

        admin = UserFactory(role='ADMIN')
        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        structure = FeeStructureFactory(level=level, term=None, program=None)

        FeeCalculationService.calculate_for_student(student, term)
        key = _fee_structure_cache_key(level.pk, None)
        assert cache.get(key) is not None

        auth_client(admin).delete(f'{FEE_STRUCTURE_LIST}{structure.pk}/')
        assert cache.get(key) is None
