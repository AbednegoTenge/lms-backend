from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q, Sum

from apps.fees.models import AdditionalFee, FeeStructure, StudentFee

_CACHE_TIMEOUT = 3600  # 1 hour


def _fee_structure_cache_key(level_id, program_id):
    return f'fee_structure:{level_id}:{program_id or "none"}'


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
    def calculate_for_student(student, term, profile=None):
        """
        Create (or update) a StudentFee for the given student and term.

        Returns the StudentFee instance, or None if no applicable FeeStructure found.
        Uses update_or_create for idempotency — safe to re-run.
        Pass `profile` (with level/program pre-fetched) when the caller already
        has it loaded, to avoid re-querying it here.
        """
        from apps.enrollment.models import StudentProfile

        if profile is None:
            try:
                profile = student.student_profile
            except StudentProfile.DoesNotExist:
                return None

        level = profile.level
        program = profile.program

        fee_structure = FeeCalculationService._find_fee_structure(level, program, term)
        if fee_structure is None:
            return None

        base_amount = fee_structure.base_amount
        additional_amount = FeeCalculationService._sum_additional_fees(level, program, term)
        total_amount = base_amount + additional_amount

        # update_or_create is idempotent; never overwrites amount_paid or payment_status
        student_fee, _ = StudentFee.objects.update_or_create(
            student=student,
            term=term,
            defaults={
                'base_amount': base_amount,
                'additional_amount': additional_amount,
                'total_amount': total_amount,
            },
        )
        return student_fee

    @staticmethod
    def _find_fee_structure(level, program, term):
        cache_key = _fee_structure_cache_key(level.pk, program.pk if program else None)
        cached = cache.get(cache_key)
        if cached is not None:
            try:
                return FeeStructure.objects.get(pk=cached)
            except FeeStructure.DoesNotExist:
                cache.delete(cache_key)

        result = FeeCalculationService._lookup_fee_structure(level, program, term)
        if result is not None:
            cache.set(cache_key, str(result.pk), _CACHE_TIMEOUT)
        return result

    @staticmethod
    def _lookup_fee_structure(level, program, term):
        base_qs = FeeStructure.objects.filter(level=level, is_active=True).order_by('-effective_from')

        # Priority 1: level + program + term
        if program and term:
            qs = base_qs.filter(program=program, term=term)
            if qs.exists():
                return qs.first()

        # Priority 2: level + program + term=null
        if program:
            qs = base_qs.filter(program=program, term__isnull=True)
            if qs.exists():
                return qs.first()

        # Priority 3: level + program=null + term
        if term:
            qs = base_qs.filter(program__isnull=True, term=term)
            if qs.exists():
                return qs.first()

        # Priority 4: level + program=null + term=null
        qs = base_qs.filter(program__isnull=True, term__isnull=True)
        if qs.exists():
            return qs.first()

        return None

    @staticmethod
    def _sum_additional_fees(level, program, term):
        q = Q(applies_to=AdditionalFee.ALL)
        q |= Q(applies_to=AdditionalFee.LEVEL, level=level)
        if program:
            q |= Q(applies_to=AdditionalFee.PROGRAM, program=program)

        result = (
            AdditionalFee.objects
            .filter(term=term, is_active=True)
            .filter(q)
            .aggregate(total=Sum('amount'))
        )
        return result['total'] or Decimal('0.00')
