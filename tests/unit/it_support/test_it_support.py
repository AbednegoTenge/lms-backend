"""
Unit tests for Phase 9 — IT Support models.

Covers:
  - SupportTicket default status is OPEN
  - PasswordResetRequest stores the hashed password
"""
import pytest

from apps.it_support.models import PasswordResetRequest, SupportTicket
from tests.factories import PasswordResetRequestFactory, SupportTicketFactory, UserFactory


@pytest.mark.django_db
class TestSupportTicketModel:

    def test_default_status_is_open(self):
        ticket = SupportTicketFactory()
        assert ticket.status == SupportTicket.OPEN

    def test_default_priority_is_medium(self):
        ticket = SupportTicketFactory()
        assert ticket.priority == SupportTicket.MEDIUM

    def test_resolved_at_is_null_by_default(self):
        ticket = SupportTicketFactory()
        assert ticket.resolved_at is None

    def test_string_representation(self):
        ticket = SupportTicketFactory(title='Login Issue')
        assert 'Login Issue' in str(ticket)


@pytest.mark.django_db
class TestPasswordResetRequestModel:

    def test_stores_password_hash(self):
        prr = PasswordResetRequestFactory(new_password_hash='pbkdf2_sha256$something')
        assert prr.new_password_hash.startswith('pbkdf2_sha256')

    def test_reason_can_be_null(self):
        prr = PasswordResetRequestFactory(reason=None)
        assert prr.reason is None
