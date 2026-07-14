from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.users.permissions import EXEMPT_PATHS


class RestrictedJWTAuthentication(JWTAuthentication):
    """
    Standard JWTAuthentication, plus a hard gate on must_change_password.

    A view's ``get_permissions()`` can be overridden per-viewset (and almost
    every viewset in this codebase does), so a permission class alone can't
    guarantee first-login-restricted users are blocked everywhere. Enforcing
    it here — where every request is authenticated the same way regardless
    of view — makes it impossible to bypass by adding a new view.
    """

    message = 'Password reset required before continuing.'

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        if not user.must_change_password:
            return result

        path = request.path.rstrip('/')
        if any(path == exempt.rstrip('/') for exempt in EXEMPT_PATHS):
            return result

        raise PermissionDenied(self.message)
