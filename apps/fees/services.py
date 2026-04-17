from decimal import Decimal

from apps.fees.models import AdditionalFee, FeeStructure, StudentFee


class FeeCalculationService:
    """
    Calculates and generates StudentFee records for a student in a given term.

    FeeStructure lookup priority (most specific first):
      1. level + program + term
      2. level + program + term=null
      3. level + program=null + term
      4. level + program=null + term=null
    """

    @staticmethod
    def calculate_for_student(student, term):
        """
        Create (or retrieve) a StudentFee for the given student and term.

        Returns the StudentFee instance, or None if no applicable FeeStructure found.
        """
        from apps.enrollment.models import StudentProfile

        try:
            profile = student.student_profile
        except StudentProfile.DoesNotExist:
            return None

        level = profile.level
        program = profile.program

        # Find the most specific active FeeStructure
        fee_structure = FeeCalculationService._find_fee_structure(level, program, term)
        if fee_structure is None:
            return None

        base_amount = fee_structure.base_amount

        # Find applicable AdditionalFees for this term
        additional_amount = FeeCalculationService._sum_additional_fees(level, program, term)

        total_amount = base_amount + additional_amount

        # create or retrieve (UNIQUE(student, term) constraint)
        student_fee, _ = StudentFee.objects.get_or_create(
            student=student,
            term=term,
            defaults={
                'base_amount': base_amount,
                'additional_amount': additional_amount,
                'total_amount': total_amount,
                'amount_paid': Decimal('0.00'),
                'payment_status': StudentFee.NOT_PAID,
            },
        )
        return student_fee

    @staticmethod
    def _find_fee_structure(level, program, term):
        candidates = (
            FeeStructure.objects
            .filter(level=level, is_active=True)
            .filter(
                # program match: exact or null
                program__in=[program] if program else []
            )
            .order_by('-effective_from')
        )

        # Priority 1: level + program + term
        if program and term:
            qs = candidates.filter(program=program, term=term)
            if qs.exists():
                return qs.first()

        # Priority 2: level + program + term=null
        if program:
            qs = candidates.filter(program=program, term__isnull=True)
            if qs.exists():
                return qs.first()

        # Priority 3: level + program=null + term
        if term:
            qs = (
                FeeStructure.objects
                .filter(level=level, program__isnull=True, term=term, is_active=True)
                .order_by('-effective_from')
            )
            if qs.exists():
                return qs.first()

        # Priority 4: level + program=null + term=null (most general)
        qs = (
            FeeStructure.objects
            .filter(level=level, program__isnull=True, term__isnull=True, is_active=True)
            .order_by('-effective_from')
        )
        if qs.exists():
            return qs.first()

        return None

    @staticmethod
    def _sum_additional_fees(level, program, term):
        qs = AdditionalFee.objects.filter(term=term, is_active=True)
        total = Decimal('0.00')
        for fee in qs:
            if fee.applies_to == AdditionalFee.ALL:
                total += fee.amount
            elif fee.applies_to == AdditionalFee.PROGRAM and program and fee.program == program:
                total += fee.amount
            elif fee.applies_to == AdditionalFee.LEVEL and fee.level == level:
                total += fee.amount
        return total
