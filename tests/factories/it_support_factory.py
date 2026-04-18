import factory
from factory.django import DjangoModelFactory

from apps.it_support.models import PasswordResetRequest, SupportTicket


class SupportTicketFactory(DjangoModelFactory):
    class Meta:
        model = SupportTicket

    raised_by = factory.SubFactory('tests.factories.user_factory.UserFactory', role='STUDENT')
    assigned_to = None
    title = factory.Sequence(lambda n: f'Ticket {n}')
    description = 'Please help.'
    category = SupportTicket.OTHER
    status = SupportTicket.OPEN
    priority = SupportTicket.MEDIUM


class PasswordResetRequestFactory(DjangoModelFactory):
    class Meta:
        model = PasswordResetRequest

    requested_for = factory.SubFactory('tests.factories.user_factory.UserFactory', role='STUDENT')
    reset_by = factory.SubFactory('tests.factories.user_factory.UserFactory', role='IT_SUPPORT')
    new_password_hash = 'pbkdf2_sha256$dummy_hash'
    reason = None
