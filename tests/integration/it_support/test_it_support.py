"""
Integration tests for Phase 9 — IT Support.

Covers:
  - Student can create own support ticket
  - All roles can create support tickets
  - Student cannot see another student's ticket (not in results)
  - IT Support can see all tickets
  - IT Support can update ticket status; resolved_at set when RESOLVED
  - Resolved ticket has resolved_at timestamp set
  - Non-IT-Support cannot PATCH ticket → 403
  - IT Support can reset any user password → must_change_password=True
  - Password reset logs to AuditLog and PasswordResetRequest
  - Non-IT-Support cannot call reset-password → 403
  - Unauthenticated cannot access tickets
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.it_support.models import PasswordResetRequest, SupportTicket
from apps.users.models import AuditLog
from tests.factories import SupportTicketFactory, UserFactory


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


TICKET_LIST = '/api/v1/support-tickets/'
RESET_PASSWORD_URL = '/api/v1/support/reset-password/'


def ticket_url(pk):
    return f'/api/v1/support-tickets/{pk}/'


def _ticket_payload(**kwargs):
    return {
        'title': 'Cannot login',
        'description': 'My password is not working.',
        'category': SupportTicket.PASSWORD_RESET,
        'priority': SupportTicket.MEDIUM,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Ticket creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSupportTicketCreate:

    def test_student_can_create_ticket(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).post(TICKET_LIST, _ticket_payload())
        assert resp.status_code == status.HTTP_201_CREATED
        assert SupportTicket.objects.filter(raised_by=student).exists()

    def test_teacher_can_create_ticket(self):
        teacher = UserFactory(role='TEACHER')
        resp = auth_client(teacher).post(TICKET_LIST, _ticket_payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_admin_can_create_ticket(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(TICKET_LIST, _ticket_payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_it_support_can_create_ticket(self):
        it = UserFactory(role='IT_SUPPORT')
        resp = auth_client(it).post(TICKET_LIST, _ticket_payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_unauthenticated_cannot_create_ticket(self):
        resp = APIClient().post(TICKET_LIST, _ticket_payload())
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_ticket_raised_by_is_requesting_user(self):
        student = UserFactory(role='STUDENT')
        auth_client(student).post(TICKET_LIST, _ticket_payload())
        ticket = SupportTicket.objects.get(raised_by=student)
        assert ticket.status == SupportTicket.OPEN


# ---------------------------------------------------------------------------
# Ticket visibility
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSupportTicketVisibility:

    def test_student_sees_only_own_tickets(self):
        student1 = UserFactory(role='STUDENT')
        student2 = UserFactory(role='STUDENT')
        SupportTicketFactory(raised_by=student1)
        SupportTicketFactory(raised_by=student2)

        resp = auth_client(student1).get(TICKET_LIST)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data['data']['results'] if 'results' in resp.data['data'] else resp.data['data']
        ids = [t['raised_by'] for t in results]
        # All tickets belong to student1
        assert all(str(i) == str(student1.pk) for i in ids)

    def test_student_cannot_retrieve_another_students_ticket(self):
        student1 = UserFactory(role='STUDENT')
        student2 = UserFactory(role='STUDENT')
        ticket = SupportTicketFactory(raised_by=student2)
        resp = auth_client(student1).get(ticket_url(ticket.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_it_support_sees_all_tickets(self):
        it = UserFactory(role='IT_SUPPORT')
        student1 = UserFactory(role='STUDENT')
        student2 = UserFactory(role='STUDENT')
        SupportTicketFactory(raised_by=student1)
        SupportTicketFactory(raised_by=student2)

        resp = auth_client(it).get(TICKET_LIST)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data['data']['results'] if 'results' in resp.data['data'] else resp.data['data']
        assert len(results) == 2

    def test_it_support_can_retrieve_any_ticket(self):
        it = UserFactory(role='IT_SUPPORT')
        student = UserFactory(role='STUDENT')
        ticket = SupportTicketFactory(raised_by=student)
        resp = auth_client(it).get(ticket_url(ticket.pk))
        assert resp.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Ticket update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSupportTicketUpdate:

    def test_it_support_can_update_status(self):
        it = UserFactory(role='IT_SUPPORT')
        ticket = SupportTicketFactory()
        resp = auth_client(it).patch(ticket_url(ticket.pk), {'status': SupportTicket.IN_PROGRESS})
        assert resp.status_code == status.HTTP_200_OK
        ticket.refresh_from_db()
        assert ticket.status == SupportTicket.IN_PROGRESS

    def test_resolved_at_set_when_status_resolved(self):
        it = UserFactory(role='IT_SUPPORT')
        ticket = SupportTicketFactory()
        resp = auth_client(it).patch(ticket_url(ticket.pk), {'status': SupportTicket.RESOLVED})
        assert resp.status_code == status.HTTP_200_OK
        ticket.refresh_from_db()
        assert ticket.status == SupportTicket.RESOLVED
        assert ticket.resolved_at is not None

    def test_student_cannot_update_ticket(self):
        student = UserFactory(role='STUDENT')
        ticket = SupportTicketFactory(raised_by=student)
        resp = auth_client(student).patch(ticket_url(ticket.pk), {'status': SupportTicket.CLOSED})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_it_support_can_assign_ticket_to_self(self):
        it = UserFactory(role='IT_SUPPORT')
        ticket = SupportTicketFactory()
        resp = auth_client(it).patch(ticket_url(ticket.pk), {'assigned_to': str(it.pk)})
        assert resp.status_code == status.HTTP_200_OK
        ticket.refresh_from_db()
        assert ticket.assigned_to_id == it.pk


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPasswordReset:

    def test_it_support_can_reset_user_password(self):
        it = UserFactory(role='IT_SUPPORT')
        student = UserFactory(role='STUDENT', must_change_password=False)
        resp = auth_client(it).post(RESET_PASSWORD_URL, {
            'user_id': str(student.pk),
            'new_password': 'NewPass123!',
            'reason': 'User forgot password',
        })
        assert resp.status_code == status.HTTP_200_OK
        student.refresh_from_db()
        assert student.must_change_password is True
        assert resp.data['data']['school_id'] == student.school_id

    def test_password_reset_logs_to_audit_log(self):
        it = UserFactory(role='IT_SUPPORT')
        student = UserFactory(role='STUDENT')
        auth_client(it).post(RESET_PASSWORD_URL, {
            'user_id': str(student.pk),
            'new_password': 'NewPass123!',
        })
        assert AuditLog.objects.filter(
            action=AuditLog.RESET_PASSWORD,
            object_id=student.pk,
        ).exists()

    def test_password_reset_creates_password_reset_request(self):
        it = UserFactory(role='IT_SUPPORT')
        student = UserFactory(role='STUDENT')
        auth_client(it).post(RESET_PASSWORD_URL, {
            'user_id': str(student.pk),
            'new_password': 'NewPass123!',
            'reason': 'forgot password',
        })
        prr = PasswordResetRequest.objects.filter(requested_for=student).first()
        assert prr is not None
        assert prr.reset_by == it
        assert prr.reason == 'forgot password'

    def test_non_it_support_cannot_reset_password(self):
        admin = UserFactory(role='ADMIN')
        student = UserFactory(role='STUDENT')
        resp = auth_client(admin).post(RESET_PASSWORD_URL, {
            'user_id': str(student.pk),
            'new_password': 'NewPass123!',
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_reset_password(self):
        student1 = UserFactory(role='STUDENT')
        student2 = UserFactory(role='STUDENT')
        resp = auth_client(student1).post(RESET_PASSWORD_URL, {
            'user_id': str(student2.pk),
            'new_password': 'NewPass123!',
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_reset_nonexistent_user_returns_404(self):
        import uuid
        it = UserFactory(role='IT_SUPPORT')
        resp = auth_client(it).post(RESET_PASSWORD_URL, {
            'user_id': str(uuid.uuid4()),
            'new_password': 'NewPass123!',
        })
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_missing_user_id_returns_400(self):
        it = UserFactory(role='IT_SUPPORT')
        resp = auth_client(it).post(RESET_PASSWORD_URL, {'new_password': 'NewPass123!'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_new_password_returns_400(self):
        it = UserFactory(role='IT_SUPPORT')
        student = UserFactory(role='STUDENT')
        resp = auth_client(it).post(RESET_PASSWORD_URL, {'user_id': str(student.pk)})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
