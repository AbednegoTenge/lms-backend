from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.models import AuditLog
from apps.users.serializers import (
    FirstLoginResetSerializer,
    LoginSerializer,
    LogoutSerializer,
    _get_client_ip,
)


class AuthThrottle(AnonRateThrottle):
    rate = '5/min'
    scope = 'auth'


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login/
# ---------------------------------------------------------------------------

class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(
                {'success': False, 'message': _first_error(serializer.errors), 'data': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        refresh['roles'] = user.get_cached_roles()
        refresh['must_change_password'] = user.must_change_password
        access = refresh.access_token
        access['roles'] = user.get_cached_roles()
        access['must_change_password'] = user.must_change_password

        AuditLog.objects.create(
            user=user,
            action=AuditLog.LOGIN,
            model_name='CustomUser',
            object_id=user.id,
            ip_address=_get_client_ip(request),
        )

        return Response({
            'success': True,
            'message': 'Login successful.',
            'data': {
                'access': str(access),
                'refresh': str(refresh),
                'force_password_reset': user.must_change_password,
                'roles': user.get_cached_roles(),
            },
        })


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh/
# ---------------------------------------------------------------------------

class TokenRefreshWrappedView(TokenRefreshView):
    """Thin wrapper that emits the standard response envelope."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            return Response({
                'success': True,
                'message': 'Token refreshed.',
                'data': response.data,
            })
        return Response(
            {'success': False, 'message': 'Invalid or expired refresh token.', 'data': {}},
            status=response.status_code,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout/
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'message': _first_error(serializer.errors), 'data': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response({'success': True, 'message': 'Logged out successfully.', 'data': {}})


# ---------------------------------------------------------------------------
# POST /api/v1/auth/first-login-reset/
# ---------------------------------------------------------------------------

class FirstLoginResetView(APIView):
    """Only accessible with a restricted (must_change_password=True) token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.must_change_password:
            return Response(
                {
                    'success': False,
                    'message': 'Password reset not required.',
                    'data': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh_token = request.data.get('refresh')
        serializer = FirstLoginResetSerializer(
            data=request.data,
            context={'request': request, 'refresh_token': refresh_token},
        )
        if not serializer.is_valid():
            return Response(
                {'success': False, 'message': _first_error(serializer.errors), 'data': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tokens = serializer.save()
        return Response({
            'success': True,
            'message': 'Password reset successfully.',
            'data': tokens,
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_error(errors: dict) -> str:
    for key, val in errors.items():
        if isinstance(val, list) and val:
            msg = val[0]
            return str(msg) if not isinstance(msg, str) else msg
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            return _first_error(val)
    return 'Validation error.'
