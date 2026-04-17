import pytest
from django.db import IntegrityError, transaction

from apps.users.models import AuditLog, CustomUser, Role, UserRole
from apps.users.services import UserService, generate_school_id
from tests.factories import RoleFactory, UserFactory


@pytest.mark.django_db(transaction=True)
class TestGenerateSchoolId:
    def test_first_student_is_std001(self):
        from apps.users.models import SchoolIDCounter
        SchoolIDCounter.objects.filter(prefix='STD').delete()
        with transaction.atomic():
            sid = generate_school_id('STUDENT')
        assert sid == 'STD001'

    def test_increments_sequentially(self):
        from apps.users.models import SchoolIDCounter
        SchoolIDCounter.objects.filter(prefix='TCH').delete()
        with transaction.atomic():
            first = generate_school_id('TEACHER')
        assert first == 'TCH001'
        with transaction.atomic():
            second = generate_school_id('TEACHER')
        assert second == 'TCH002'

    def test_different_prefixes_are_independent(self):
        from apps.users.models import SchoolIDCounter
        SchoolIDCounter.objects.filter(prefix__in=['ADM', 'STD']).delete()
        with transaction.atomic():
            adm = generate_school_id('ADMIN')
            std = generate_school_id('STUDENT')
        assert adm.startswith('ADM')
        assert std.startswith('STD')
        assert adm != std

    def test_it_support_prefix(self):
        from apps.users.models import SchoolIDCounter
        SchoolIDCounter.objects.filter(prefix='IT').delete()
        with transaction.atomic():
            sid = generate_school_id('IT_SUPPORT')
        assert sid.startswith('IT')

    def test_super_admin_prefix(self):
        from apps.users.models import SchoolIDCounter
        SchoolIDCounter.objects.filter(prefix='SA').delete()
        with transaction.atomic():
            sid = generate_school_id('SUPER_ADMIN')
        assert sid.startswith('SA')


@pytest.mark.django_db(transaction=True)
class TestUserServiceCreateUser:
    def test_creates_user_with_must_change_password_true(self):
        # Ensure roles exist
        Role.objects.get_or_create(name='STUDENT')
        user = UserService.create_user(
            first_name='Bob',
            last_name='Builder',
            email='bob@school.test',
            password='AdminSet1!',
            roles=['STUDENT'],
        )
        assert user.must_change_password is True

    def test_school_id_generated_from_role(self):
        Role.objects.get_or_create(name='TEACHER')
        CustomUser.objects.filter(school_id__startswith='TCH').delete()
        user = UserService.create_user(
            first_name='Tina',
            last_name='Teacher',
            email='tina@school.test',
            password='AdminSet1!',
            roles=['TEACHER'],
        )
        assert user.school_id.startswith('TCH')

    def test_role_assigned_to_user(self):
        Role.objects.get_or_create(name='PRINCIPAL')
        user = UserService.create_user(
            first_name='Paul',
            last_name='Pal',
            email='paul@school.test',
            password='AdminSet1!',
            roles=['PRINCIPAL'],
        )
        roles = list(
            UserRole.objects.filter(user=user).values_list('role__name', flat=True)
        )
        assert 'PRINCIPAL' in roles

    def test_multiple_roles_assigned(self):
        Role.objects.get_or_create(name='TEACHER')
        Role.objects.get_or_create(name='ADMIN')
        user = UserService.create_user(
            first_name='Multi',
            last_name='Role',
            email='multi@school.test',
            password='AdminSet1!',
            roles=['TEACHER', 'ADMIN'],
        )
        roles = list(
            UserRole.objects.filter(user=user).values_list('role__name', flat=True)
        )
        assert 'TEACHER' in roles
        assert 'ADMIN' in roles

    def test_audit_log_created(self):
        Role.objects.get_or_create(name='STUDENT')
        user = UserService.create_user(
            first_name='Log',
            last_name='Me',
            email='logme@school.test',
            password='AdminSet1!',
            roles=['STUDENT'],
        )
        assert AuditLog.objects.filter(
            object_id=user.id, action=AuditLog.CREATE
        ).exists()

    def test_no_roles_raises_value_error(self):
        with pytest.raises(ValueError, match='At least one role'):
            UserService.create_user(
                first_name='X',
                last_name='Y',
                email='xy@school.test',
                password='AdminSet1!',
                roles=[],
            )

    def test_unknown_role_raises_value_error(self):
        with pytest.raises(ValueError):
            UserService.create_user(
                first_name='X',
                last_name='Y',
                email='xy2@school.test',
                password='AdminSet1!',
                roles=['UNKNOWN_ROLE'],
            )

    def test_concurrent_create_no_duplicate_school_id(self):
        """Two threads creating students must not produce the same school_id."""
        from concurrent.futures import ThreadPoolExecutor
        from apps.users.models import SchoolIDCounter

        Role.objects.get_or_create(name='STUDENT')
        # Reset counter so IDs start fresh for this test
        SchoolIDCounter.objects.filter(prefix='STD').delete()

        results = []
        errors = []

        def create_student(i):
            try:
                u = UserService.create_user(
                    first_name=f'User{i}',
                    last_name='Concurrent',
                    email=f'concurrent{i}@school.test',
                    password='AdminSet1!',
                    roles=['STUDENT'],
                )
                results.append(u.school_id)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_student, i) for i in range(5)]
            for f in futures:
                f.result()

        assert not errors, f'Errors during concurrent creation: {errors}'
        assert len(results) == len(set(results)), 'Duplicate school_ids generated'


@pytest.mark.django_db(transaction=True)
class TestResetPasswordByIT:
    def test_sets_must_change_password_true(self):
        Role.objects.get_or_create(name='STUDENT')
        Role.objects.get_or_create(name='IT_SUPPORT')
        student = UserFactory(role='STUDENT', must_change_password=False)
        it_user = UserFactory(role='IT_SUPPORT', must_change_password=False)

        UserService.reset_password_by_it(
            target_user=student,
            new_password='NewPass99!',
            reset_by=it_user,
        )

        student.refresh_from_db()
        assert student.must_change_password is True

    def test_audit_log_created(self):
        Role.objects.get_or_create(name='STUDENT')
        Role.objects.get_or_create(name='IT_SUPPORT')
        student = UserFactory(role='STUDENT', must_change_password=False)
        it_user = UserFactory(role='IT_SUPPORT', must_change_password=False)

        UserService.reset_password_by_it(
            target_user=student,
            new_password='NewPass99!',
            reset_by=it_user,
        )

        assert AuditLog.objects.filter(
            user=it_user,
            action=AuditLog.RESET_PASSWORD,
            object_id=student.id,
        ).exists()
