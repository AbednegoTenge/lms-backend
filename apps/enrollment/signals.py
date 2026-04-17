from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.academics.models import Term
from apps.enrollment.models import StudentProfile


@receiver(post_save, sender=StudentProfile)
def auto_enroll_core_courses(sender, instance, created, **kwargs):
    """On new StudentProfile creation, enroll in all active CORE courses for the current term."""
    if not created:
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
