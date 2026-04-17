from celery import shared_task


@shared_task
def mark_overdue_fees(term_id):
    """
    Mark all StudentFees for the given term as OVERDUE if they are
    NOT_PAID or PARTIALLY_PAID.  Called after a term transitions away.
    """
    from apps.fees.models import StudentFee

    return StudentFee.objects.filter(
        term_id=term_id,
        payment_status__in=[StudentFee.NOT_PAID, StudentFee.PARTIALLY_PAID],
    ).update(payment_status=StudentFee.OVERDUE)


@shared_task
def generate_term_fees():
    """
    Generate StudentFee records for all ACTIVE students for the current term.
    Idempotent: get_or_create inside calculate_for_student prevents duplicates.
    """
    from apps.academics.models import Term
    from apps.enrollment.models import StudentProfile
    from apps.fees.services import FeeCalculationService

    current_term = Term.objects.filter(is_current=True).first()
    if current_term is None:
        return 0

    profiles = StudentProfile.objects.filter(status=StudentProfile.ACTIVE).select_related('user')
    count = 0
    for profile in profiles:
        result = FeeCalculationService.calculate_for_student(profile.user, current_term)
        if result is not None:
            count += 1
    return count
