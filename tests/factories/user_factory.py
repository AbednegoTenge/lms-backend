import factory
from factory.django import DjangoModelFactory

from apps.users.models import CustomUser, Role, UserRole
from apps.users.services import ROLE_PREFIX


class RoleFactory(DjangoModelFactory):
    class Meta:
        model = Role
        django_get_or_create = ('name',)

    name = factory.Iterator([
        Role.STUDENT, Role.TEACHER, Role.ADMIN,
        Role.PRINCIPAL, Role.IT_SUPPORT, Role.SUPER_ADMIN,
    ])


class UserRoleFactory(DjangoModelFactory):
    class Meta:
        model = UserRole

    user = factory.SubFactory('tests.factories.user_factory.UserFactory')
    role = factory.SubFactory(RoleFactory)
    is_active = True


class UserFactory(DjangoModelFactory):
    """Creates a CustomUser with a single role.

    Usage:
        UserFactory()                    # default role = STUDENT
        UserFactory(role='TEACHER')
        UserFactory(must_change_password=True)
        UserFactory(role='ADMIN', password='CustomPass1!')
    """

    class Meta:
        model = CustomUser

    # Simple sequential school_id — unique in tests; prefix accuracy is not required
    school_id = factory.Sequence(lambda n: f'U{n:05d}')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.LazyAttribute(lambda obj: f'{obj.school_id.lower()}@school.test')
    must_change_password = False
    is_active = True

    @factory.post_generation
    def role(obj, create, extracted, **kwargs):
        """Assign a role to the user after creation.

        Pass role as a keyword arg: UserFactory(role='ADMIN')
        extracted will be 'ADMIN' in this method.
        """
        if not create:
            return
        role_name = extracted or 'STUDENT'
        role_obj, _ = Role.objects.get_or_create(name=role_name)
        UserRole.objects.get_or_create(user=obj, role=role_obj, defaults={'is_active': True})

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'TestPass123!')
        obj = model_class(**kwargs)
        obj.set_password(password)
        obj.save()
        return obj
