"""
Integration tests for Phase 8 — Announcements.

Covers:
  - Admin/Principal/IT Support can create
  - Teacher/Student cannot create → 403
  - Publish: creator can publish, triggers fan_out
  - GET /announcements/ returns only announcements for requesting user
  - Student cannot see announcement not addressed to them
  - Mark as read → is_read=True, read_at set
  - ?is_read=false filter works (unread count correct)
  - Non-creator cannot edit/delete
  - Cannot edit/delete published announcement
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.announcements.models import Announcement, AnnouncementRecipient
from tests.factories import (
    AnnouncementFactory,
    AnnouncementRecipientFactory,
    LevelFactory,
    ProgramFactory,
    StudentProfileFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


ANNOUNCEMENT_LIST = '/api/v1/announcements/'


def announcement_url(pk):
    return f'/api/v1/announcements/{pk}/'


def publish_url(pk):
    return f'/api/v1/announcements/{pk}/publish/'


def read_url(pk):
    return f'/api/v1/announcements/{pk}/read/'


# ---------------------------------------------------------------------------
# Create permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAnnouncementCreate:

    def _payload(self):
        return {
            'title': 'Test Announcement',
            'body': 'This is a test.',
            'recipient_type': Announcement.ALL,
        }

    def test_admin_can_create(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_201_CREATED
        assert Announcement.objects.filter(created_by=admin).exists()

    def test_principal_can_create(self):
        principal = UserFactory(role='PRINCIPAL')
        resp = auth_client(principal).post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_it_support_can_create(self):
        it = UserFactory(role='IT_SUPPORT')
        resp = auth_client(it).post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_teacher_cannot_create(self):
        teacher = UserFactory(role='TEACHER')
        resp = auth_client(teacher).post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_create(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_create(self):
        resp = APIClient().post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_created_announcement_is_unpublished(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(ANNOUNCEMENT_LIST, self._payload())
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['data']['is_published'] is False


# ---------------------------------------------------------------------------
# Publish + fan-out
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAnnouncementPublish:

    def test_creator_can_publish(self):
        admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)
        resp = auth_client(admin).post(publish_url(ann.pk))
        assert resp.status_code == status.HTTP_200_OK
        ann.refresh_from_db()
        assert ann.is_published is True
        assert ann.published_at is not None

    def test_publish_fans_out_all_recipients(self):
        admin = UserFactory(role='ADMIN')
        teacher = UserFactory(role='TEACHER')
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)
        auth_client(admin).post(publish_url(ann.pk))
        # Both admin and teacher should have recipient rows
        assert AnnouncementRecipient.objects.filter(announcement=ann, user=admin).exists()
        assert AnnouncementRecipient.objects.filter(announcement=ann, user=teacher).exists()

    def test_non_creator_cannot_publish(self):
        admin = UserFactory(role='ADMIN')
        other_admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)
        resp = auth_client(other_admin).post(publish_url(ann.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_already_published_returns_400(self):
        admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin,
                                   is_published=True)
        resp = auth_client(admin).post(publish_url(ann.pk))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_by_program_fanout_correct(self):
        admin = UserFactory(role='ADMIN')
        prog = ProgramFactory(name='GENERAL_ARTS', code='GA')
        level = LevelFactory()
        student = UserFactory(role='STUDENT')
        StudentProfileFactory(user=student, level=level, program=prog)

        ann = AnnouncementFactory(
            recipient_type=Announcement.BY_PROGRAM,
            program=prog,
            created_by=admin,
        )
        auth_client(admin).post(publish_url(ann.pk))
        assert AnnouncementRecipient.objects.filter(announcement=ann, user=student).exists()


# ---------------------------------------------------------------------------
# List — only own announcements
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAnnouncementList:

    def test_user_sees_only_own_announcements(self):
        admin = UserFactory(role='ADMIN')
        user1 = UserFactory(role='TEACHER')
        user2 = UserFactory(role='TEACHER')

        ann1 = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)
        ann2 = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)

        # Manually add recipients so we control who gets what
        AnnouncementRecipientFactory(announcement=ann1, user=user1)
        AnnouncementRecipientFactory(announcement=ann2, user=user2)

        resp = auth_client(user1).get(ANNOUNCEMENT_LIST)
        data = resp.data['data']
        ids = [str(d['id']) for d in data]
        assert str(ann1.pk) in ids
        assert str(ann2.pk) not in ids

    def test_student_cannot_see_announcement_not_addressed_to_them(self):
        admin = UserFactory(role='ADMIN')
        student = UserFactory(role='STUDENT')
        other_student = UserFactory(role='STUDENT')

        ann = AnnouncementFactory(recipient_type=Announcement.ALL, created_by=admin)
        # Only add recipient for other_student
        AnnouncementRecipientFactory(announcement=ann, user=other_student)

        resp = auth_client(student).get(ANNOUNCEMENT_LIST)
        ids = [str(d['id']) for d in resp.data['data']]
        assert str(ann.pk) not in ids

    def test_is_read_annotated_in_list(self):
        admin = UserFactory(role='ADMIN')
        user = UserFactory(role='TEACHER')
        ann = AnnouncementFactory(created_by=admin)
        AnnouncementRecipientFactory(announcement=ann, user=user, is_read=False)

        resp = auth_client(user).get(ANNOUNCEMENT_LIST)
        items = resp.data['data']
        assert len(items) == 1
        assert items[0]['is_read'] is False

    def test_is_read_filter_returns_only_unread(self):
        admin = UserFactory(role='ADMIN')
        user = UserFactory(role='TEACHER')
        ann_read = AnnouncementFactory(created_by=admin)
        ann_unread = AnnouncementFactory(created_by=admin)
        AnnouncementRecipientFactory(announcement=ann_read, user=user, is_read=True)
        AnnouncementRecipientFactory(announcement=ann_unread, user=user, is_read=False)

        resp = auth_client(user).get(ANNOUNCEMENT_LIST + '?is_read=false')
        ids = [str(d['id']) for d in resp.data['data']]
        assert str(ann_unread.pk) in ids
        assert str(ann_read.pk) not in ids

    def test_unread_count_via_filter(self):
        admin = UserFactory(role='ADMIN')
        user = UserFactory(role='TEACHER')
        for _ in range(3):
            ann = AnnouncementFactory(created_by=admin)
            AnnouncementRecipientFactory(announcement=ann, user=user, is_read=False)
        # One read announcement
        ann_r = AnnouncementFactory(created_by=admin)
        AnnouncementRecipientFactory(announcement=ann_r, user=user, is_read=True)

        resp = auth_client(user).get(ANNOUNCEMENT_LIST + '?is_read=false')
        assert len(resp.data['data']) == 3


# ---------------------------------------------------------------------------
# Mark as read
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMarkAsRead:

    def test_mark_as_read_sets_is_read_and_read_at(self):
        admin = UserFactory(role='ADMIN')
        user = UserFactory(role='TEACHER')
        ann = AnnouncementFactory(created_by=admin)
        AnnouncementRecipientFactory(announcement=ann, user=user, is_read=False)

        resp = auth_client(user).post(read_url(ann.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['data']['is_read'] is True
        assert resp.data['data']['read_at'] is not None

        from apps.announcements.models import AnnouncementRecipient
        r = AnnouncementRecipient.objects.get(announcement=ann, user=user)
        assert r.is_read is True
        assert r.read_at is not None

    def test_mark_as_read_idempotent(self):
        admin = UserFactory(role='ADMIN')
        user = UserFactory(role='TEACHER')
        ann = AnnouncementFactory(created_by=admin)
        AnnouncementRecipientFactory(announcement=ann, user=user, is_read=False)

        auth_client(user).post(read_url(ann.pk))
        resp = auth_client(user).post(read_url(ann.pk))
        assert resp.status_code == status.HTTP_200_OK

    def test_mark_as_read_not_recipient_returns_404(self):
        admin = UserFactory(role='ADMIN')
        stranger = UserFactory(role='TEACHER')
        ann = AnnouncementFactory(created_by=admin)
        resp = auth_client(stranger).post(read_url(ann.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Edit / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAnnouncementEditDelete:

    def test_creator_can_edit_unpublished(self):
        admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(created_by=admin, is_published=False)
        resp = auth_client(admin).patch(announcement_url(ann.pk), {'title': 'Updated'})
        assert resp.status_code == status.HTTP_200_OK

    def test_non_creator_cannot_edit(self):
        admin = UserFactory(role='ADMIN')
        other = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(created_by=admin, is_published=False)
        resp = auth_client(other).patch(announcement_url(ann.pk), {'title': 'Hacked'})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_edit_published_announcement(self):
        admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(created_by=admin, is_published=True)
        resp = auth_client(admin).patch(announcement_url(ann.pk), {'title': 'Changed'})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_creator_can_delete_unpublished(self):
        admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(created_by=admin, is_published=False)
        resp = auth_client(admin).delete(announcement_url(ann.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not Announcement.objects.filter(pk=ann.pk).exists()

    def test_cannot_delete_published_announcement(self):
        admin = UserFactory(role='ADMIN')
        ann = AnnouncementFactory(created_by=admin, is_published=True)
        resp = auth_client(admin).delete(announcement_url(ann.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN
