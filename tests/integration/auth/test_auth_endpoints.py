import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import AuditLog, CustomUser, Role
from tests.factories import UserFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login(client, school_id, password):
    return client.post(
        '/api/v1/auth/login/',
        {'school_id': school_id, 'password': password},
        format='json',
    )


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoginEndpoint:
    def setup_method(self):
        self.client = APIClient()

    def test_login_with_school_id_succeeds(self):
        user = UserFactory(role='STUDENT', must_change_password=False)
        user.set_password('pass123Word!')
        user.save()

        resp = login(self.client, user.school_id, 'pass123Word!')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['success'] is True
        assert 'access' in resp.data['data']
        assert 'refresh' in resp.data['data']

    def test_login_returns_force_password_reset_false(self):
        user = UserFactory(role='ADMIN', must_change_password=False)
        user.set_password('AdminPass1!')
        user.save()

        resp = login(self.client, user.school_id, 'AdminPass1!')
        assert resp.data['data']['force_password_reset'] is False

    def test_login_returns_force_password_reset_true(self):
        user = UserFactory(role='TEACHER', must_change_password=True)
        user.set_password('TeachPass1!')
        user.save()

        resp = login(self.client, user.school_id, 'TeachPass1!')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['data']['force_password_reset'] is True

    def test_email_login_rejected(self):
        user = UserFactory(role='STUDENT', must_change_password=False)
        user.set_password('pass123Word!')
        user.save()

        # Use email as the school_id field — should fail
        resp = login(self.client, user.email, 'pass123Word!')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_wrong_password_rejected(self):
        user = UserFactory(role='STUDENT', must_change_password=False)
        user.set_password('CorrectPass1!')
        user.save()

        resp = login(self.client, user.school_id, 'WrongPass1!')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_creates_audit_log(self):
        user = UserFactory(role='ADMIN', must_change_password=False)
        user.set_password('LogTest1!')
        user.save()

        login(self.client, user.school_id, 'LogTest1!')
        assert AuditLog.objects.filter(user=user, action=AuditLog.LOGIN).exists()

    def test_login_includes_roles(self):
        user = UserFactory(role='PRINCIPAL', must_change_password=False)
        user.set_password('PrincipalP1!')
        user.save()

        resp = login(self.client, user.school_id, 'PrincipalP1!')
        assert 'PRINCIPAL' in resp.data['data']['roles']

    def test_inactive_user_cannot_login(self):
        user = UserFactory(role='STUDENT', must_change_password=False, is_active=False)
        user.set_password('pass123Word!')
        user.save()

        resp = login(self.client, user.school_id, 'pass123Word!')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Refresh endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRefreshEndpoint:
    def setup_method(self):
        self.client = APIClient()

    def test_valid_refresh_returns_new_access(self):
        user = UserFactory(role='STUDENT', must_change_password=False)
        refresh = RefreshToken.for_user(user)

        resp = self.client.post(
            '/api/v1/auth/refresh/',
            {'refresh': str(refresh)},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['success'] is True
        assert 'access' in resp.data['data']

    def test_invalid_refresh_returns_error(self):
        resp = self.client.post(
            '/api/v1/auth/refresh/',
            {'refresh': 'not.a.valid.token'},
            format='json',
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Logout endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLogoutEndpoint:
    def setup_method(self):
        self.client = APIClient()

    def test_logout_blacklists_token(self):
        user = UserFactory(role='STUDENT', must_change_password=False)
        refresh = RefreshToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}'
        )

        resp = self.client.post(
            '/api/v1/auth/logout/',
            {'refresh': str(refresh)},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['success'] is True

        # Using the same refresh token again should fail
        resp2 = self.client.post(
            '/api/v1/auth/refresh/',
            {'refresh': str(refresh)},
            format='json',
        )
        assert resp2.status_code != status.HTTP_200_OK

    def test_unauthenticated_logout_returns_401(self):
        resp = self.client.post(
            '/api/v1/auth/logout/',
            {'refresh': 'some.token'},
            format='json',
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# RequiresPasswordChange gate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRequiresPasswordChange:
    """A restricted token (must_change_password=True) must be blocked on all
    endpoints except /auth/first-login-reset/ and /auth/logout/."""

    def setup_method(self):
        self.client = APIClient()

    def _restricted_client(self):
        user = UserFactory(role='STUDENT', must_change_password=True)
        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}'
        )
        return client, user, refresh

    def test_restricted_token_blocked_on_protected_endpoint(self):
        """Use the refresh endpoint as a stand-in for any protected resource."""
        client, user, refresh = self._restricted_client()

        # A hypothetical protected endpoint — we use a custom dummy view or
        # verify the permission class itself.
        from apps.users.permissions import RequiresPasswordChange, EXEMPT_PATHS
        from unittest.mock import MagicMock

        perm = RequiresPasswordChange()
        request = MagicMock()
        request.user = user
        request.path = '/api/v1/students/'
        assert perm.has_permission(request, None) is False

    def test_restricted_token_allowed_on_first_login_reset(self):
        from apps.users.permissions import RequiresPasswordChange
        from unittest.mock import MagicMock

        user = UserFactory(role='STUDENT', must_change_password=True)
        perm = RequiresPasswordChange()
        request = MagicMock()
        request.user = user
        request.path = '/api/v1/auth/first-login-reset/'
        assert perm.has_permission(request, None) is True

    def test_restricted_token_allowed_on_logout(self):
        from apps.users.permissions import RequiresPasswordChange
        from unittest.mock import MagicMock

        user = UserFactory(role='STUDENT', must_change_password=True)
        perm = RequiresPasswordChange()
        request = MagicMock()
        request.user = user
        request.path = '/api/v1/auth/logout/'
        assert perm.has_permission(request, None) is True


# ---------------------------------------------------------------------------
# First-login reset endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFirstLoginResetEndpoint:
    def setup_method(self):
        self.client = APIClient()

    def _user_and_client(self):
        user = UserFactory(role='STUDENT', must_change_password=True)
        user.set_password('OldAdminPass1!')
        user.save()
        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}'
        )
        return user, client, str(refresh)

    def test_successful_reset_sets_must_change_false(self):
        user, client, refresh_str = self._user_and_client()

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'NewSecure99!',
                'new_password_confirm': 'NewSecure99!',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data['success'] is True
        assert 'access' in resp.data['data']
        assert 'refresh' in resp.data['data']

        user.refresh_from_db()
        assert user.must_change_password is False

    def test_successful_reset_creates_audit_log(self):
        user, client, refresh_str = self._user_and_client()

        client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'NewSecure99!',
                'new_password_confirm': 'NewSecure99!',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert AuditLog.objects.filter(
            user=user, action=AuditLog.FIRST_LOGIN_RESET
        ).exists()

    def test_same_password_rejected(self):
        user, client, refresh_str = self._user_and_client()

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'OldAdminPass1!',
                'new_password_confirm': 'OldAdminPass1!',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_mismatch_rejected(self):
        user, client, refresh_str = self._user_and_client()

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'NewSecure99!',
                'new_password_confirm': 'DifferentPass1!',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_rejected(self):
        user, client, refresh_str = self._user_and_client()

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'weak',
                'new_password_confirm': 'weak',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_uppercase_password_rejected(self):
        user, client, refresh_str = self._user_and_client()

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'nouppercase1!',
                'new_password_confirm': 'nouppercase1!',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_digit_password_rejected(self):
        user, client, refresh_str = self._user_and_client()

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'NoDigitsHere!',
                'new_password_confirm': 'NoDigitsHere!',
                'refresh': refresh_str,
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_already_changed_user_gets_400(self):
        user = UserFactory(role='ADMIN', must_change_password=False)
        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}'
        )

        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'NewSecure99!',
                'new_password_confirm': 'NewSecure99!',
                'refresh': str(refresh),
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.post(
            '/api/v1/auth/first-login-reset/',
            {
                'new_password': 'NewSecure99!',
                'new_password_confirm': 'NewSecure99!',
            },
            format='json',
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
