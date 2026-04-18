import factory
from factory.django import DjangoModelFactory

from apps.announcements.models import Announcement, AnnouncementRecipient


class AnnouncementFactory(DjangoModelFactory):
    class Meta:
        model = Announcement

    title = factory.Sequence(lambda n: f'Announcement {n + 1}')
    body = factory.Faker('paragraph')
    created_by = factory.SubFactory('tests.factories.user_factory.UserFactory', role='ADMIN')
    recipient_type = Announcement.ALL
    program = None
    level = None
    is_published = False
    published_at = None


class AnnouncementRecipientFactory(DjangoModelFactory):
    class Meta:
        model = AnnouncementRecipient

    announcement = factory.SubFactory(AnnouncementFactory)
    user = factory.SubFactory('tests.factories.user_factory.UserFactory')
    is_read = False
    read_at = None
