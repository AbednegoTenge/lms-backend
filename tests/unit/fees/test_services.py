"""
Unit tests for FeeCalculationService and StudentFee.save() payment status logic.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.fees.models import AdditionalFee, FeeStructure, StudentFee
from apps.fees.services import FeeCalculationService, _fee_structure_cache_key
from tests.factories import (
    AdditionalFeeFactory,
    FeeStructureFactory,
    LevelFactory,
    ProgramFactory,
    StudentFeeFactory,
    StudentProfileFactory,
    TermFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# StudentFee.save() payment status
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentFeePaymentStatus:
    def _make_fee(self, base, paid, status=None):
        fee = StudentFeeFactory(
            base_amount=base,
            total_amount=base,
            amount_paid=paid,
        )
        if status:
            StudentFee.objects.filter(pk=fee.pk).update(payment_status=status)
            fee.refresh_from_db()
        return fee

    def test_zero_paid_is_not_paid(self):
        fee = self._make_fee(Decimal('500.00'), Decimal('0.00'))
        assert fee.payment_status == StudentFee.NOT_PAID

    def test_partial_payment_is_partially_paid(self):
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('200.00'),
        )
        assert fee.payment_status == StudentFee.PARTIALLY_PAID

    def test_full_payment_is_fully_paid(self):
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('500.00'),
        )
        assert fee.payment_status == StudentFee.FULLY_PAID

    def test_overpayment_is_fully_paid(self):
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('600.00'),
        )
        assert fee.payment_status == StudentFee.FULLY_PAID

    def test_overdue_preserved_by_save(self):
        """OVERDUE set externally is never overridden by save()."""
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )
        StudentFee.objects.filter(pk=fee.pk).update(payment_status=StudentFee.OVERDUE)
        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.OVERDUE

        # Calling save() must not flip it back
        fee.save()
        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.OVERDUE

    def test_overdue_with_new_payment_stays_overdue(self):
        """Saving after adding amount_paid does not override OVERDUE."""
        fee = StudentFeeFactory(
            base_amount=Decimal('500.00'),
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )
        StudentFee.objects.filter(pk=fee.pk).update(payment_status=StudentFee.OVERDUE)
        fee.refresh_from_db()

        fee.amount_paid = Decimal('200.00')
        fee.save()
        fee.refresh_from_db()
        assert fee.payment_status == StudentFee.OVERDUE


# ---------------------------------------------------------------------------
# FeeCalculationService
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeCalculationService:
    def setup_method(self):
        from django.core.cache import cache
        cache.clear()

    def test_base_plus_additional_aggregated_correctly(self):
        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        profile = StudentProfileFactory(user=student, level=level, program=None)

        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('500.00'))
        AdditionalFeeFactory(
            term=term, applies_to=AdditionalFee.ALL, amount=Decimal('50.00')
        )
        AdditionalFeeFactory(
            term=term, applies_to=AdditionalFee.LEVEL, level=level, amount=Decimal('30.00')
        )

        result = FeeCalculationService.calculate_for_student(student, term)
        assert result is not None
        assert result.base_amount == Decimal('500.00')
        assert result.additional_amount == Decimal('80.00')
        assert result.total_amount == Decimal('580.00')

    def test_program_specific_fee_only_for_matching_program(self):
        level = LevelFactory(number=1)
        prog_arts = ProgramFactory(name='GENERAL_ARTS', code='GA')
        prog_sci = ProgramFactory(name='GENERAL_SCIENCE', code='GS')
        term = TermFactory()

        student_arts = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student_arts, level=level, program=prog_arts)
        student_sci = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student_sci, level=level, program=prog_sci)

        FeeStructureFactory(level=level, program=None, term=None, base_amount=Decimal('500.00'))
        AdditionalFeeFactory(
            term=term,
            applies_to=AdditionalFee.PROGRAM,
            program=prog_arts,
            amount=Decimal('100.00'),
        )

        arts_fee = FeeCalculationService.calculate_for_student(student_arts, term)
        sci_fee = FeeCalculationService.calculate_for_student(student_sci, term)

        assert arts_fee.additional_amount == Decimal('100.00')
        assert sci_fee.additional_amount == Decimal('0.00')

    def test_no_fee_structure_returns_none(self):
        level = LevelFactory(number=2)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)

        result = FeeCalculationService.calculate_for_student(student, term)
        assert result is None

    def test_no_student_profile_returns_none(self):
        term = TermFactory()
        # User with no StudentProfile
        student = UserFactory(role='STUDENT')
        result = FeeCalculationService.calculate_for_student(student, term)
        assert result is None

    def test_idempotent_second_call_returns_same_record(self):
        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('400.00'))

        fee1 = FeeCalculationService.calculate_for_student(student, term)
        fee2 = FeeCalculationService.calculate_for_student(student, term)
        assert fee1.pk == fee2.pk

    def test_fee_structure_priority_level_program_term_wins(self):
        """Priority 1 (level+program+term) beats level-only."""
        level = LevelFactory(number=1)
        program = ProgramFactory(name='BUSINESS', code='BUS')
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=program)

        # General fallback
        FeeStructureFactory(level=level, program=None, term=None, base_amount=Decimal('300.00'))
        # Most specific
        FeeStructureFactory(level=level, program=program, term=term, base_amount=Decimal('700.00'))

        fee = FeeCalculationService.calculate_for_student(student, term)
        assert fee.base_amount == Decimal('700.00')


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeStructureCache:
    def setup_method(self):
        from django.core.cache import cache
        cache.clear()

    def test_cache_populated_after_first_lookup(self):
        from django.core.cache import cache

        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        structure = FeeStructureFactory(level=level, term=None, program=None)

        FeeCalculationService.calculate_for_student(student, term)

        key = _fee_structure_cache_key(level.pk, None)
        assert cache.get(key) == str(structure.pk)

    def test_cache_invalidated_on_update(self):
        from django.core.cache import cache

        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        structure = FeeStructureFactory(level=level, term=None, program=None, base_amount=Decimal('400.00'))

        FeeCalculationService.calculate_for_student(student, term)
        key = _fee_structure_cache_key(level.pk, None)
        assert cache.get(key) is not None

        # Update triggers signal → cache.delete_pattern
        structure.base_amount = Decimal('600.00')
        structure.save()

        assert cache.get(key) is None

    def test_cache_invalidated_on_delete(self):
        from django.core.cache import cache

        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        structure = FeeStructureFactory(level=level, term=None, program=None)

        FeeCalculationService.calculate_for_student(student, term)
        key = _fee_structure_cache_key(level.pk, None)
        assert cache.get(key) is not None

        structure.delete()
        assert cache.get(key) is None

    def test_second_call_uses_cache(self):
        """_lookup_fee_structure not called on second calculate."""
        level = LevelFactory(number=1)
        term = TermFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=None)
        FeeStructureFactory(level=level, term=None, program=None)

        # First call is real — populates cache
        fee1 = FeeCalculationService.calculate_for_student(student, term)

        # Second call: cache hit — _lookup_fee_structure must NOT be invoked
        with patch.object(FeeCalculationService, '_lookup_fee_structure') as mock_lookup:
            fee2 = FeeCalculationService.calculate_for_student(student, term)
            mock_lookup.assert_not_called()

        assert fee1.pk == fee2.pk
