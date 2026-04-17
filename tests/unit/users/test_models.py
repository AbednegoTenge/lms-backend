import pytest
from django.core.cache import cache

from apps.users.models import AuditLog, CustomUser, Role, UserRole
from tests.factories import UserFactory, RoleFactory, UserRoleFactory


@pytest.mark.django_db
class TestCustomUser:
    def test_str(self):
        user = UserFactory(first_name='Jane', last_name='Doe')
        assert 'Jane Doe' in str(user)

    def test_get_full_name(self):
        user = UserFactory(first_name='Alice', last_name='Smith')
        assert user.get_full_name() == 'Alice Smith'

    def test_must_change_password_default_false_in_factory(self):
        user = UserFactory()
        assert user.must_change_password is False

    def test_must_change_password_override(self):
        user = UserFactory(must_change_password=True)
        assert user.must_change_password is True

    def test_school_id_unique(self):
        u1 = UserFactory(role='TEACHER')
        u2 = UserFactory(role='TEACHER')
        assert u1.school_id != u2.school_id

    def test_username_field_is_school_id(self):
        assert CustomUser.USERNAME_FIELD == 'school_id'


@pytest.mark.django_db
class TestRoleCaching:
    def setup_method(self):
        cache.clear()

    def test_has_role_true(self):
        user = UserFactory(role='ADMIN')
        assert user.has_role('ADMIN') is True

    def test_has_role_false(self):
        user = UserFactory(role='ADMIN')
        assert user.has_role('STUDENT') is False

    def test_has_any_role_single_match(self):
        user = UserFactory(role='TEACHER')
        assert user.has_any_role(['TEACHER', 'ADMIN']) is True

    def test_has_any_role_no_match(self):
        user = UserFactory(role='STUDENT')
        assert user.has_any_role(['ADMIN', 'PRINCIPAL']) is False

    def test_multi_role_union(self):
        """A user with TEACHER + ADMIN roles should satisfy both checks."""
        user = UserFactory(role='TEACHER')
        admin_role = Role.objects.get(name='ADMIN')
        UserRole.objects.create(user=user, role=admin_role)
        cache.clear()
        assert user.has_role('TEACHER') is True
        assert user.has_role('ADMIN') is True

    def test_role_cache_populated(self):
        user = UserFactory(role='STUDENT')
        cache.clear()
        roles = user.get_cached_roles()
        cached = cache.get(f'user:{user.id}:roles')
        assert cached == roles

    def test_invalidate_role_cache(self):
        user = UserFactory(role='STUDENT')
        _ = user.get_cached_roles()  # populate cache
        user.invalidate_role_cache()
        assert cache.get(f'user:{user.id}:roles') is None


@pytest.mark.django_db
class TestAuditLog:
    def test_create_audit_log(self):
        user = UserFactory(role='ADMIN')
        log = AuditLog.objects.create(
            user=user,
            action=AuditLog.CREATE,
            model_name='CustomUser',
            object_id=user.id,
        )
        assert log.action == AuditLog.CREATE
        assert log.user == user

    def test_audit_log_null_user(self):
        """System actions have null user."""
        log = AuditLog.objects.create(
            user=None,
            action=AuditLog.LOGIN,
            model_name='CustomUser',
            object_id=None,
        )
        assert log.user is None
