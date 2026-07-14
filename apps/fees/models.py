import uuid
from decimal import Decimal

from django.db import models

from apps.academics.models import Level, Program, Term
from apps.users.models import CustomUser


class FeeStructure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.ForeignKey(
        Level,
        on_delete=models.CASCADE,
        related_name='fee_structures',
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_structures',
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_structures',
    )
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=200)
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_fee_structures',
    )

    class Meta:
        db_table = 'fee_structures'
        ordering = ['-effective_from']

    def __str__(self):
        return f'FeeStructure: Level {self.level.number} — {self.base_amount}'


class AdditionalFee(models.Model):
    ALL = 'ALL'
    PROGRAM = 'PROGRAM'
    LEVEL = 'LEVEL'
    APPLIES_TO_CHOICES = [(ALL, 'All'), (PROGRAM, 'Program'), (LEVEL, 'Level')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    applies_to = models.CharField(max_length=10, choices=APPLIES_TO_CHOICES)
    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='additional_fees',
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='additional_fees',
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='additional_fees',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'additional_fees'

    def __str__(self):
        return f'{self.name} — {self.amount}'


class StudentFee(models.Model):
    NOT_PAID = 'NOT_PAID'
    PARTIALLY_PAID = 'PARTIALLY_PAID'
    FULLY_PAID = 'FULLY_PAID'
    OVERDUE = 'OVERDUE'

    PAYMENT_STATUS_CHOICES = [
        (NOT_PAID, 'Not Paid'),
        (PARTIALLY_PAID, 'Partially Paid'),
        (FULLY_PAID, 'Fully Paid'),
        (OVERDUE, 'Overdue'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='student_fees',
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='student_fees',
    )
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    additional_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=NOT_PAID,
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'student_fees'
        unique_together = [('student', 'term')]

    def save(self, *args, **kwargs):
        # A full payment always resolves the fee, even one previously marked
        # OVERDUE by term transition — otherwise a paid-off fee stays stuck
        # as OVERDUE forever, since mark_overdue_fees() never revisits it.
        if self.amount_paid >= self.total_amount and self.total_amount > 0:
            self.payment_status = self.FULLY_PAID
        elif self.payment_status == self.OVERDUE:
            pass  # still overdue until fully paid, regardless of partial payments
        elif self.amount_paid > 0:
            self.payment_status = self.PARTIALLY_PAID
        else:
            self.payment_status = self.NOT_PAID
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.student.school_id} — Term {self.term} — {self.payment_status}'


class Payment(models.Model):
    CASH = 'CASH'
    BANK_TRANSFER = 'BANK_TRANSFER'
    MOBILE_MONEY = 'MOBILE_MONEY'
    OTHER = 'OTHER'

    PAYMENT_METHOD_CHOICES = [
        (CASH, 'Cash'),
        (BANK_TRANSFER, 'Bank Transfer'),
        (MOBILE_MONEY, 'Mobile Money'),
        (OTHER, 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_fee = models.ForeignKey(
        StudentFee,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference = models.CharField(max_length=100, null=True, blank=True)
    recorded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_payments',
    )
    paid_at = models.DateTimeField()
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-paid_at']

    def __str__(self):
        return f'Payment {self.amount} for {self.student_fee}'
