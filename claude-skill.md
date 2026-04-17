# Claude Skill — School Management System

This skill is loaded on-demand by Claude Code when working on the SMS Django project.
It provides domain-specific patterns, anti-patterns, and code templates
so Claude generates consistent, production-ready code every time.

Load with: `/skill sms` or reference `@docs/claude-skill.md` in a prompt.

---

## Domain Rules (critical — always apply)

1. **Login uses `school_id`, not email.** `USERNAME_FIELD = 'school_id'` on `CustomUser`. Never use email as an auth credential — it is informational only.
2. **`school_id` is always server-generated.** Call `generate_school_id(primary_role)` inside `UserService.create_user()`. Admin never provides or sees this value in the request body. Format: `STD001`, `TCH003`, `ADM001`, `PRI001`, `IT002`, `SA001`.
3. **`school_id` generation is transactional.** Always inside `select_for_update()` to prevent race conditions on concurrent user creation. Never generate outside a `transaction.atomic()` block.
4. **Admin sets the initial password.** Passed in the `POST /users/` request body, stored hashed. No auto-generation. `must_change_password` is always set `True` on creation — never bypassed.
5. **First-login restricted token blocks all endpoints except two.** When `must_change_password=True`, the JWT issued at login is valid but restricted by `RequiresPasswordChange`. Only `POST /auth/first-login-reset/` and `POST /auth/logout/` are reachable. Everything else returns HTTP 403. Apply `RequiresPasswordChange` in `DEFAULT_PERMISSION_CLASSES` globally.
6. **IT Support reset re-triggers the first-login flow.** `POST /support/reset-password/` sets `must_change_password=True`. The user must go through `/auth/first-login-reset/` on next login. It does NOT return the new password to the caller — password is communicated out-of-band.
7. **Core course enrollment is signal-driven.** Never call `EnrollmentService.enroll_core_courses()` from a view directly. It is always triggered by `post_save` on `StudentProfile`.
8. **Exactly 4 electives.** The constraint `len(course_ids) == 4` must be validated in the serializer AND enforced by a DB check constraint. Reject anything else with HTTP 400.
9. **Term transition is transactional.** Any term transition logic must be inside `transaction.atomic()` with `select_for_update()` on the affected rows.
10. **Fees auto-compute.** `StudentFee.payment_status` is computed in `save()`. Never set it directly except for `OVERDUE` (set by the transition task).
11. **JWT claims include roles and `must_change_password`.** The custom token serializer injects both. Middleware reads from the token — never hits the DB on every request for roles.
12. **IT Support created by Super Admin only.** The `POST /users/` endpoint must check: if `roles` includes `IT_SUPPORT`, require `request.user.has_role('SUPER_ADMIN')`.
13. **Status fields are never manually toggled.** Quiz/Assignment status transitions are handled by Celery Beat or explicit service methods — never accept `status` as a write field in any serializer.

---

## `school_id` Generation Template

```python
# apps/users/services.py

PREFIX_MAP = {
    'STUDENT':    'STD',
    'TEACHER':    'TCH',
    'ADMIN':      'ADM',
    'PRINCIPAL':  'PRI',
    'IT_SUPPORT': 'IT',
    'SUPER_ADMIN': 'SA',
}

def generate_school_id(primary_role: str) -> str:
    """
    Generate the next sequential school_id for a given role.
    Must be called inside an existing transaction.atomic() + select_for_update block.
    """
    prefix = PREFIX_MAP[primary_role]
    last = (
        CustomUser.objects
        .select_for_update()
        .filter(school_id__startswith=prefix)
        .order_by('-school_id')
        .first()
    )
    next_num = 1 if last is None else int(last.school_id[len(prefix):]) + 1
    return f"{prefix}{next_num:03d}"


class UserService:

    @staticmethod
    def create_user(validated_data: dict, created_by) -> CustomUser:
        """
        Create a new user with a server-generated school_id.
        Admin provides: first_name, last_name, email, password, roles (list).
        """
        roles = validated_data.pop('roles')          # e.g. ['TEACHER']
        password = validated_data.pop('password')
        primary_role = roles[0]                       # first role drives the ID prefix

        with transaction.atomic():
            school_id = generate_school_id(primary_role)
            user = CustomUser.objects.create(
                school_id=school_id,
                must_change_password=True,            # ALWAYS True on creation
                **validated_data
            )
            user.set_password(password)
            user.save(update_fields=['password'])

            for role_name in roles:
                role = Role.objects.get(name=role_name)
                UserRole.objects.create(user=user, role=role, assigned_by=created_by)

        AuditLog.objects.create(
            user=created_by,
            action='CREATE',
            model_name='CustomUser',
            object_id=user.id,
            diff={'school_id': school_id, 'roles': roles},
        )
        return user
```

---

## First-Login Reset Service Template

```python
# apps/users/services.py  (continued)

class AuthService:

    @staticmethod
    def first_login_reset(user: CustomUser, new_password: str) -> dict:
        """
        Complete the first-login password reset.
        Returns a fresh token pair after resetting must_change_password.
        Raises ValueError on policy violations.
        """
        if not user.must_change_password:
            raise ValueError("Password reset not required for this account.")

        # Policy: new password must differ from the stored (admin-set) one
        if user.check_password(new_password):
            raise ValueError("New password must differ from the temporary password.")

        # Policy: strength check
        AuthService._validate_password_strength(new_password)

        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])

        AuditLog.objects.create(
            user=user,
            action='FIRST_LOGIN_RESET',
            model_name='CustomUser',
            object_id=user.id,
            diff={},
        )

        # Issue fresh unrestricted token pair
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }

    @staticmethod
    def _validate_password_strength(password: str):
        import re
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not re.search(r'[A-Z]', password):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r'\d', password):
            raise ValueError("Password must contain at least one digit.")
```

---

## `RequiresPasswordChange` Permission Template

```python
# apps/users/permissions.py

class RequiresPasswordChange(BasePermission):
    """
    Global guard: blocks all endpoints for users with must_change_password=True,
    except the first-login reset and logout endpoints.
    Add to DEFAULT_PERMISSION_CLASSES in settings.
    """
    message = "Password reset required before continuing."

    EXEMPT_PATHS = {
        '/api/v1/auth/first-login-reset/',
        '/api/v1/auth/logout/',
    }

    def has_permission(self, request, view):
        # Unauthenticated — let IsAuthenticated handle it
        if not request.user or not request.user.is_authenticated:
            return True
        if request.user.must_change_password:
            return request.path in self.EXEMPT_PATHS
        return True
```

```python
# config/settings/base.py
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        'apps.users.permissions.RequiresPasswordChange',  # ← global guard
    ],
    ...
}
```

---

## User Create Serializer Template

```python
# apps/users/serializers.py

class UserCreateSerializer(serializers.Serializer):
    first_name    = serializers.CharField(max_length=100)
    last_name     = serializers.CharField(max_length=100)
    email         = serializers.EmailField(required=False, allow_blank=True)
    phone         = serializers.CharField(max_length=20, required=False)
    password      = serializers.CharField(write_only=True, min_length=8)
    roles         = serializers.ListField(
        child=serializers.ChoiceField(choices=Role.ROLE_CHOICES),
        min_length=1
    )

    # school_id is NOT in this serializer — it is generated server-side

    def validate_roles(self, roles):
        request_user = self.context['request'].user
        if 'IT_SUPPORT' in roles and not request_user.has_role('SUPER_ADMIN'):
            raise serializers.ValidationError(
                "Only Super Admin can create IT Support accounts."
            )
        if 'SUPER_ADMIN' in roles and not request_user.has_role('SUPER_ADMIN'):
            raise serializers.ValidationError(
                "Only Super Admin can assign Super Admin role."
            )
        return roles

    def create(self, validated_data):
        return UserService.create_user(
            validated_data,
            created_by=self.context['request'].user
        )
```

---

Always use this — never return raw serializer data:

```python
# apps/core/responses.py
from rest_framework.response import Response

def success_response(data=None, message="Success.", status=200):
    return Response({
        "success": True,
        "data": data,
        "message": message
    }, status=status)

def error_response(message="An error occurred.", errors=None, status=400):
    return Response({
        "success": False,
        "data": None,
        "message": message,
        "errors": errors or {}
    }, status=status)
```

---

## Standard ViewSet Template

```python
# apps/<app>/views.py
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from apps.core.responses import success_response, error_response
from apps.users.permissions import IsAdmin, IsAdminOrPrincipal
from .models import MyModel
from .serializers import MyModelSerializer
from .services import MyModelService

class MyModelViewSet(ModelViewSet):
    serializer_class = MyModelSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        # ALWAYS use select_related / prefetch_related
        return MyModel.objects.select_related(
            'related_fk_field'
        ).prefetch_related(
            'related_m2m_field'
        ).filter(is_active=True)

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        # log to AuditLog
        AuditLog.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='MyModel',
            object_id=instance.id,
            diff={},
            ip_address=get_client_ip(self.request)
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def custom_action(self, request, pk=None):
        instance = self.get_object()
        try:
            result = MyModelService.do_something(instance, request.user)
            return success_response(data=result, message="Action completed.")
        except ValueError as e:
            return error_response(message=str(e), status=422)
```

---

## Standard Service Layer Template

```python
# apps/<app>/services.py
from django.db import transaction
from .models import MyModel

class MyModelService:

    @staticmethod
    def create(validated_data, created_by):
        """Create and return a new instance."""
        with transaction.atomic():
            instance = MyModel.objects.create(
                **validated_data,
                created_by=created_by
            )
            return instance

    @staticmethod
    def do_business_logic(instance, actor):
        """
        Describe what this does.
        Raises ValueError if business rule violated.
        """
        if not instance.can_do_thing():
            raise ValueError("Cannot perform this action in current state.")
        with transaction.atomic():
            instance.some_field = 'new_value'
            instance.save(update_fields=['some_field', 'updated_at'])
        return instance
```

---

## Standard Serializer Template

```python
# apps/<app>/serializers.py
from rest_framework import serializers
from .models import MyModel

class MyModelSerializer(serializers.ModelSerializer):

    class Meta:
        model = MyModel
        fields = ['id', 'name', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']  # never writable

    def validate(self, attrs):
        # Cross-field validation goes here
        return attrs

    def validate_some_field(self, value):
        if len(value) < 3:
            raise serializers.ValidationError("Must be at least 3 characters.")
        return value
```

---

## Enrollment Serializer (4-elective constraint)

```python
class ElectiveEnrollmentSerializer(serializers.Serializer):
    course_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=4,
        max_length=4,
        error_messages={
            'min_length': 'Exactly 4 elective courses must be selected.',
            'max_length': 'Exactly 4 elective courses must be selected.',
        }
    )

    def validate_course_ids(self, course_ids):
        student = self.context['student']
        courses = Course.objects.filter(
            id__in=course_ids,
            course_type='ELECTIVE',
            program=student.studentprofile.program,
            is_active=True
        )
        if courses.count() != 4:
            raise serializers.ValidationError(
                "All courses must be active electives for the student's program."
            )
        return course_ids
```

---

## N+1 Checklist

Before submitting any queryset for review, verify:

```python
# For every FK accessed in the serializer: select_related
# For every M2M or reverse FK: prefetch_related
# For computed annotations: use .annotate() not Python loops

# Example: course list with teacher name
Course.objects.select_related(
    'teachercourseassignment__teacher'  # FK chain
).prefetch_related(
    'enrollment_set'  # reverse FK
).annotate(
    enrolled_count=Count('enrollment', filter=Q(enrollment__is_active=True))
)
```

---

## Factory Template

```python
# tests/factories/<app>.py
import factory
from factory.django import DjangoModelFactory
from apps.<app>.models import MyModel

class MyModelFactory(DjangoModelFactory):
    class Meta:
        model = MyModel

    name = factory.Sequence(lambda n: f"Test Item {n}")
    is_active = True
    created_by = factory.SubFactory('tests.factories.users.UserFactory')

    class Params:
        # Use traits for common variant states
        inactive = factory.Trait(is_active=False)
```

---

## Permission Test Pattern

```python
# Use parametrize for permission matrix tests
@pytest.mark.parametrize("role,expected_status", [
    ('ADMIN', 200),
    ('PRINCIPAL', 200),
    ('TEACHER', 403),
    ('STUDENT', 403),
    ('IT_SUPPORT', 403),
])
@pytest.mark.django_db
def test_endpoint_permission_matrix(api_client, role, expected_status):
    user = UserFactory()
    RoleFactory.assign(user, role)
    api_client.force_authenticate(user=user)
    response = api_client.get('/api/v1/some-endpoint/')
    assert response.status_code == expected_status
```

---

## Celery Task Template

```python
# apps/<app>/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

logger = get_task_logger(__name__)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(Exception,),
)
def my_background_task(self, some_id):
    logger.info(f"Starting task for {some_id}")
    try:
        # ... do work
        logger.info(f"Task completed for {some_id}")
    except Exception as exc:
        logger.error(f"Task failed for {some_id}: {exc}")
        raise self.retry(exc=exc)
```

---

## Common Anti-Patterns to Avoid

```python
# ❌ NEVER — login with email
{ "email": "user@school.gh", "password": "..." }

# ✅ ALWAYS — login with school_id
{ "school_id": "STD042", "password": "..." }

# ❌ NEVER — generate school_id outside a transaction
school_id = generate_school_id(role)   # race condition: two concurrent calls get same ID
user = CustomUser.objects.create(school_id=school_id, ...)

# ✅ ALWAYS — generate inside transaction.atomic() + select_for_update
with transaction.atomic():
    school_id = generate_school_id(role)  # select_for_update inside keeps it safe
    user = CustomUser.objects.create(school_id=school_id, ...)

# ❌ NEVER — allow must_change_password to be skipped
user = CustomUser.objects.create(must_change_password=False, ...)  # WRONG

# ✅ ALWAYS — set in service, never overridden
user = CustomUser.objects.create(must_change_password=True, ...)  # set by UserService

# ❌ NEVER — raw status set from outside
fee.payment_status = 'FULLY_PAID'
fee.save()

# ✅ ALWAYS — record payment, let save() compute status
Payment.objects.create(student_fee=fee, amount=amount, ...)
# save() signal recomputes status

# ❌ NEVER — inline business logic in views
def post(self, request):
    if Enrollment.objects.filter(student=...).count() >= 4:
        ...

# ✅ ALWAYS — service layer
EnrollmentService.enroll_electives(student, course_ids, actor)

# ❌ NEVER — loop queryset for aggregation
total = sum(fee.total_amount for fee in StudentFee.objects.all())

# ✅ ALWAYS — DB aggregation
from django.db.models import Sum
total = StudentFee.objects.aggregate(total=Sum('total_amount'))['total']

# ❌ NEVER — N+1 in queryset
Quiz.objects.all()  # then serializer accesses quiz.assignment.course

# ✅ ALWAYS
Quiz.objects.select_related('assignment__course').all()
```

---

## File Upload Pattern

```python
# apps/assessments/validators.py
import magic

ALLOWED_MIME_TYPES = {
    'application/pdf',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'video/mp4',
}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

def validate_upload(file):
    if file.size > MAX_UPLOAD_SIZE:
        raise ValidationError("File too large. Max 50MB.")
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    if mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(f"File type not allowed: {mime}")
```
