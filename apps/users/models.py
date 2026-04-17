import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.cache import cache


class CustomUserManager(BaseUserManager):

    def create_user(self, school_id, password=None, **extra_fields):
        if not school_id:
            raise ValueError('School Id is required')
        user = self.model(school_id=school_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, school_id, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('must_change_password', False)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(school_id, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_id = models.CharField(max_length=20, unique=True)
    email = models.EmailField(max_length=255, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)

    objects = CustomUserManager()
    USERNAME_FIELD = 'school_id'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f'{self.school_id} — {self.get_full_name()}'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_cached_roles(self):
        key = f'user:{self.id}:roles'
        roles = cache.get(key)
        if roles is None:
            roles = list(
                self.userrole_set.filter(is_active=True)
                .select_related('role')
                .values_list('role__name', flat=True)
            )
            cache.set(key, roles, timeout=900)  # 15 min
        return roles

    def has_role(self, role_name):
        return role_name in self.get_cached_roles()

    def has_any_role(self, role_names):
        return bool(set(role_names) & set(self.get_cached_roles()))

    def invalidate_role_cache(self):
        cache.delete(f'user:{self.id}:roles')


class Role(models.Model):
    STUDENT = 'STUDENT'
    TEACHER = 'TEACHER'
    ADMIN = 'ADMIN'
    PRINCIPAL = 'PRINCIPAL'
    IT_SUPPORT = 'IT_SUPPORT'
    SUPER_ADMIN = 'SUPER_ADMIN'

    ROLE_CHOICES = [
        (STUDENT, 'Student'),
        (TEACHER, 'Teacher'),
        (ADMIN, 'Admin'),
        (PRINCIPAL, 'Principal'),
        (IT_SUPPORT, 'IT Support'),
        (SUPER_ADMIN, 'Super Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)

    class Meta:
        db_table = 'roles'

    def __str__(self):
        return self.name


class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_roles',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_roles'
        unique_together = [('user', 'role')]

    def __str__(self):
        return f'{self.user.school_id} — {self.role.name}'


class SchoolIDCounter(models.Model):
    """One row per role prefix; acts as the authoritative sequence counter.

    select_for_update on this row serialises concurrent school_id generation.
    """
    prefix = models.CharField(max_length=10, primary_key=True)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'school_id_counters'

    def __str__(self):
        return f'{self.prefix}: {self.last_value}'


class AuditLog(models.Model):
    CREATE = 'CREATE'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    LOGIN = 'LOGIN'
    RESET_PASSWORD = 'RESET_PASSWORD'
    FIRST_LOGIN_RESET = 'FIRST_LOGIN_RESET'

    ACTION_CHOICES = [
        (CREATE, 'Create'),
        (UPDATE, 'Update'),
        (DELETE, 'Delete'),
        (LOGIN, 'Login'),
        (RESET_PASSWORD, 'Reset Password'),
        (FIRST_LOGIN_RESET, 'First Login Reset'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.UUIDField(null=True, blank=True)
    diff = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.action} by {self.user} at {self.timestamp}'
