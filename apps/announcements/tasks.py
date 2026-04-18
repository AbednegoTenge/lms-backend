import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def fan_out_announcement(announcement_id):
    from apps.announcements.models import Announcement, AnnouncementRecipient
    from apps.enrollment.models import StudentProfile
    from apps.users.models import CustomUser, UserRole

    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist:
        logger.warning('fan_out_announcement: announcement %s not found', announcement_id)
        return 0

    rt = announcement.recipient_type

    if rt == Announcement.ALL:
        users = CustomUser.objects.filter(is_active=True)
    elif rt == Announcement.ALL_STUDENTS:
        student_ids = StudentProfile.objects.filter(
            status=StudentProfile.ACTIVE
        ).values_list('user_id', flat=True)
        users = CustomUser.objects.filter(pk__in=student_ids, is_active=True)
    elif rt == Announcement.ALL_TEACHERS:
        teacher_ids = UserRole.objects.filter(
            role__name='TEACHER', is_active=True
        ).values_list('user_id', flat=True)
        users = CustomUser.objects.filter(pk__in=teacher_ids, is_active=True)
    elif rt == Announcement.BY_PROGRAM:
        student_ids = StudentProfile.objects.filter(
            program=announcement.program
        ).values_list('user_id', flat=True)
        users = CustomUser.objects.filter(pk__in=student_ids, is_active=True)
    elif rt == Announcement.BY_LEVEL:
        student_ids = StudentProfile.objects.filter(
            level=announcement.level
        ).values_list('user_id', flat=True)
        users = CustomUser.objects.filter(pk__in=student_ids, is_active=True)
    elif rt == Announcement.PRINCIPAL:
        principal_ids = UserRole.objects.filter(
            role__name='PRINCIPAL', is_active=True
        ).values_list('user_id', flat=True)
        users = CustomUser.objects.filter(pk__in=principal_ids, is_active=True)
    elif rt == Announcement.SPECIFIC_USERS:
        users = announcement.specific_users.filter(is_active=True)
    else:
        users = CustomUser.objects.none()

    recipients = [
        AnnouncementRecipient(announcement=announcement, user=user)
        for user in users
    ]
    AnnouncementRecipient.objects.bulk_create(recipients, ignore_conflicts=True)
    count = len(recipients)
    logger.info('Announcement %s fanned out to %d recipients', announcement_id, count)
    return count
