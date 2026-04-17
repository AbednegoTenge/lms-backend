from celery import shared_task
from django.utils import timezone


@shared_task
def close_expired_quizzes():
    """Mark all OPEN quizzes whose due_datetime has passed as CLOSED."""
    from apps.assessments.models import Quiz

    updated = Quiz.objects.filter(
        status=Quiz.OPEN,
        due_datetime__lte=timezone.now(),
    ).update(status=Quiz.CLOSED)
    return updated


@shared_task
def close_expired_assignments():
    """Mark all OPEN assignments whose due_datetime has passed as CLOSED."""
    from apps.assessments.models import Assignment

    updated = Assignment.objects.filter(
        status=Assignment.OPEN,
        due_datetime__lte=timezone.now(),
    ).update(status=Assignment.CLOSED)
    return updated
