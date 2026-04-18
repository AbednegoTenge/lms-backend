"""
Unit tests for the fan_out_announcement Celery task.
"""
import pytest

from apps.announcements.models import Announcement, AnnouncementRecipient
from apps.announcements.tasks import fan_out_announcement
from tests.factories import (
    AnnouncementFactory,
    LevelFactory,
    ProgramFactory,
    StudentProfileFactory,
    UserFactory,
)


def _make_student(level=None, program=None):
    user = UserFactory(role='STUDENT')
    StudentProfileFactory(user=user, level=level or LevelFactory(), program=program)
    return user


@pytest.mark.django_db
class TestFanOutAnnouncement:

    def test_all_recipients_get_rows(self):
        u1 = UserFactory(role='ADMIN')
        u2 = UserFactory(role='TEACHER')
        u3 = _make_student()
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=u1)

        count = fan_out_announcement(str(ann.pk))

        all_active = count  # task returns number created
        # All 3 users + the creator are active — check each got a row
        for u in [u1, u2, u3]:
            assert AnnouncementRecipient.objects.filter(announcement=ann, user=u).exists()

    def test_all_students_only_gets_students(self):
        admin = UserFactory(role='ADMIN')
        teacher = UserFactory(role='TEACHER')
        student = _make_student()
        ann = AnnouncementFactory(recipient_type=Announcement.ALL_STUDENTS, created_by=admin)

        fan_out_announcement(str(ann.pk))

        assert AnnouncementRecipient.objects.filter(announcement=ann, user=student).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=teacher).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=admin).exists()

    def test_all_teachers_only_gets_teachers(self):
        admin = UserFactory(role='ADMIN')
        teacher = UserFactory(role='TEACHER')
        student = _make_student()
        ann = AnnouncementFactory(recipient_type=Announcement.ALL_TEACHERS, created_by=admin)

        fan_out_announcement(str(ann.pk))

        assert AnnouncementRecipient.objects.filter(announcement=ann, user=teacher).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=student).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=admin).exists()

    def test_by_program_only_gets_matching_program(self):
        admin = UserFactory(role='ADMIN')
        prog_arts = ProgramFactory(name='GENERAL_ARTS', code='GA')
        prog_sci = ProgramFactory(name='GENERAL_SCIENCE', code='GS')
        level = LevelFactory()

        student_arts = _make_student(level=level, program=prog_arts)
        student_sci = _make_student(level=level, program=prog_sci)

        ann = AnnouncementFactory(
            recipient_type=Announcement.BY_PROGRAM, program=prog_arts, created_by=admin
        )
        fan_out_announcement(str(ann.pk))

        assert AnnouncementRecipient.objects.filter(announcement=ann, user=student_arts).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=student_sci).exists()

    def test_by_level_only_gets_matching_level(self):
        admin = UserFactory(role='ADMIN')
        level1 = LevelFactory(number=1)
        level2 = LevelFactory(number=2)

        student_l1 = _make_student(level=level1)
        student_l2 = _make_student(level=level2)

        ann = AnnouncementFactory(
            recipient_type=Announcement.BY_LEVEL, level=level1, created_by=admin
        )
        fan_out_announcement(str(ann.pk))

        assert AnnouncementRecipient.objects.filter(announcement=ann, user=student_l1).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=student_l2).exists()

    def test_principal_recipient_type(self):
        admin = UserFactory(role='ADMIN')
        principal = UserFactory(role='PRINCIPAL')
        teacher = UserFactory(role='TEACHER')

        ann = AnnouncementFactory(recipient_type=Announcement.PRINCIPAL, created_by=admin)
        fan_out_announcement(str(ann.pk))

        assert AnnouncementRecipient.objects.filter(announcement=ann, user=principal).exists()
        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=teacher).exists()

    def test_idempotent_fanout_no_duplicates(self):
        admin = UserFactory(role='ADMIN')
        UserFactory(role='TEACHER')
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)

        fan_out_announcement(str(ann.pk))
        fan_out_announcement(str(ann.pk))  # second run must not duplicate

        # Each user appears exactly once
        from django.db.models import Count
        duplicates = (
            AnnouncementRecipient.objects
            .filter(announcement=ann)
            .values('user')
            .annotate(cnt=Count('user'))
            .filter(cnt__gt=1)
        )
        assert not duplicates.exists()

    def test_inactive_users_excluded(self):
        admin = UserFactory(role='ADMIN')
        inactive = UserFactory(role='TEACHER', is_active=False)
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)

        fan_out_announcement(str(ann.pk))

        assert not AnnouncementRecipient.objects.filter(announcement=ann, user=inactive).exists()

    def test_nonexistent_announcement_returns_zero(self):
        import uuid
        result = fan_out_announcement(str(uuid.uuid4()))
        assert result == 0
