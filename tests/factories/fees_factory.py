import datetime
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.fees.models import AdditionalFee, FeeStructure, Payment, StudentFee


class FeeStructureFactory(DjangoModelFactory):
    class Meta:
        model = FeeStructure

    level = factory.SubFactory('tests.factories.academics_factory.LevelFactory')
    program = None
    term = None
    base_amount = Decimal('500.00')
    description = factory.Sequence(lambda n: f'Fee Structure {n}')
    effective_from = factory.LazyFunction(lambda: datetime.date(2024, 1, 1))
    is_active = True
    created_by = None


class AdditionalFeeFactory(DjangoModelFactory):
    class Meta:
        model = AdditionalFee

    name = factory.Sequence(lambda n: f'Additional Fee {n}')
    amount = Decimal('50.00')
    applies_to = AdditionalFee.ALL
    program = None
    level = None
    term = factory.SubFactory('tests.factories.academics_factory.TermFactory')
    is_active = True


class StudentFeeFactory(DjangoModelFactory):
    class Meta:
        model = StudentFee

    student = factory.SubFactory('tests.factories.user_factory.UserFactory', role='STUDENT')
    term = factory.SubFactory('tests.factories.academics_factory.TermFactory')
    base_amount = Decimal('500.00')
    additional_amount = Decimal('0.00')
    total_amount = Decimal('500.00')
    amount_paid = Decimal('0.00')
    payment_status = StudentFee.NOT_PAID


class PaymentFactory(DjangoModelFactory):
    class Meta:
        model = Payment

    student_fee = factory.SubFactory(StudentFeeFactory)
    amount = Decimal('100.00')
    payment_method = Payment.CASH
    reference = None
    recorded_by = factory.SubFactory('tests.factories.user_factory.UserFactory', role='ADMIN')
    paid_at = factory.LazyFunction(
        lambda: datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    )
    notes = None
