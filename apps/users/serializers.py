import re

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import AuditLog, CustomUser
from apps.users.services import ROLE_PREFIX

# Reverse map: 'STD' → 'STUDENT', 'TCH' → 'TEACHER', etc.
_PREFIX_TO_ROLE = {prefix: role for role, prefix in ROLE_PREFIX.items()}


# ---------------------------------------------------------------------------
# Custom JWT token serializer — injects extra claims
# ---------------------------------------------------------------------------

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds `roles` and `must_change_password` to the JWT payload."""

    @classmethod
    def get_token(cls, user: CustomUser):
        token = super().get_token(user)
        token['roles'] = user.get_cached_roles()
        token['must_change_password'] = user.must_change_password
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['force_password_reset'] = self.user.must_change_password
        data['roles'] = self.user.get_cached_roles()
        return data


# ---------------------------------------------------------------------------
# Login serializer (wraps the token pair result in the standard envelope)
# ---------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    school_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        school_id = attrs['school_id']
        password = attrs['password']
        request = self.context.get('request')

        user = authenticate(request=request, school_id=school_id, password=password)
        if not user:
            raise serializers.ValidationError('Invalid school ID or password.')
        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')

        # Validate school_id prefix matches one of the user's roles.
        # e.g. STD001 → role must include STUDENT; TCH003 → must include TEACHER.
        claimed_role = next(
            (role for prefix, role in _PREFIX_TO_ROLE.items() if school_id.startswith(prefix)),
            None,
        )
        if claimed_role and not user.has_role(claimed_role):
            raise serializers.ValidationError('Invalid school ID or password.')

        attrs['user'] = user
        return attrs


# ---------------------------------------------------------------------------
# First-login password reset serializer
# ---------------------------------------------------------------------------

PASSWORD_RE = re.compile(r'^(?=.*[A-Z])(?=.*\d).{8,}$')


class FirstLoginResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        if not PASSWORD_RE.match(value):
            raise serializers.ValidationError(
                'Password must be at least 8 characters and contain '
                'at least one uppercase letter and one digit.'
            )
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )
        user: CustomUser = self.context['request'].user
        if check_password(attrs['new_password'], user.password):
            raise serializers.ValidationError(
                {'new_password': 'New password must differ from the current password.'}
            )
        return attrs

    def save(self, **kwargs):
        user: CustomUser = self.context['request'].user
        request = self.context['request']

        # Blacklist the current refresh token if provided
        refresh_token = self.context.get('refresh_token')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # Token already blacklisted or invalid — ignore

        user.set_password(self.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        user.invalidate_role_cache()

        # Issue fresh unrestricted token pair
        refresh = RefreshToken.for_user(user)
        refresh['roles'] = user.get_cached_roles()
        refresh['must_change_password'] = False
        access = refresh.access_token
        access['roles'] = user.get_cached_roles()
        access['must_change_password'] = False

        AuditLog.objects.create(
            user=user,
            action=AuditLog.FIRST_LOGIN_RESET,
            model_name='CustomUser',
            object_id=user.id,
            ip_address=_get_client_ip(request),
        )

        return {
            'access': str(access),
            'refresh': str(refresh),
        }


# ---------------------------------------------------------------------------
# Logout serializer
# ---------------------------------------------------------------------------

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        try:
            token = RefreshToken(attrs['refresh'])
            attrs['token'] = token
        except Exception:
            raise serializers.ValidationError({'refresh': 'Invalid or expired token.'})
        return attrs

    def save(self, **kwargs):
        self.validated_data['token'].blacklist()


class TeacherSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'school_id',
            'full_name',
            'first_name',
            'last_name',
            'email',
            'phone',
            'is_active',
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request) -> str | None:
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
