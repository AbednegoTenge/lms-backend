from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.academics.models import Term
from apps.enrollment.models import StudentProfile


@receiver(post_save, sender=StudentProfile)
def auto_enroll_core_courses(sender, instance, created, **kwargs):
    """
    Enroll the student in all active CORE courses for the current term.

    Fires on initial StudentProfile creation, and again whenever a program is
    (re)assigned: StudentViewSet.assign_program sets the transient
    `_enroll_core_courses` flag and saves instead of calling EnrollmentService
    directly, so core enrollment always happens through this signal.
    """
    if not created and not getattr(instance, '_enroll_core_courses', False):
        return

    current_term = Term.objects.filter(is_current=True).first()
    if current_term is None:
        return

    # Import here to avoid circular imports at module load time
    from apps.enrollment.services import EnrollmentService
    EnrollmentService.enroll_core_courses(
        student=instance.user,
        term=current_term,
        level=instance.level,
    )
