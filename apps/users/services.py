from django.db import transaction

from apps.users.models import AuditLog, CustomUser, Role, SchoolIDCounter, UserRole

# Maps role name → school_id prefix
ROLE_PREFIX = {
    Role.STUDENT: 'STD',
    Role.TEACHER: 'TCH',
    Role.ADMIN: 'ADM',
    Role.PRINCIPAL: 'PRI',
    Role.IT_SUPPORT: 'IT',
    Role.SUPER_ADMIN: 'SA',
}


def generate_school_id(primary_role: str) -> str:
    """Return next available school_id for the given role prefix.

    Must be called inside a transaction (handled by UserService.create_user).
    Uses a dedicated SchoolIDCounter row with select_for_update to serialise
    concurrent calls — prevents race conditions even when no users exist yet.
    """
    prefix = ROLE_PREFIX[primary_role]
    # get_or_create + select_for_update:
    # Step 1: ensure the counter row exists (no lock yet, may race on creation)
    SchoolIDCounter.objects.get_or_create(prefix=prefix)
    # Step 2: lock the row exclusively for this transaction
    counter = SchoolIDCounter.objects.select_for_update().get(prefix=prefix)
    counter.last_value += 1
    counter.save(update_fields=['last_value'])
    return f'{prefix}{counter.last_value:03d}'


class UserService:

    @staticmethod
    @transaction.atomic
    def create_user(
        *,
        first_name: str,
        last_name: str,
        email: str | None,
        password: str,
        roles: list[str],
        phone: str | None = None,
        created_by: CustomUser | None = None,
        ip_address: str | None = None,
    ) -> CustomUser:
        """Create a user, assign roles, and log to AuditLog.

        The primary role (first in the list) determines school_id prefix.
        Must-change-password is always True on creation.
        """
        if not roles:
            raise ValueError('At least one role must be provided.')

        primary_role = roles[0]
        if primary_role not in ROLE_PREFIX:
            raise ValueError(f'Unknown role: {primary_role}')

        school_id = generate_school_id(primary_role)

        user = CustomUser(
            school_id=school_id,
            first_name=first_name,
            last_name=last_name,
            email=email or None,
            phone=phone,
            must_change_password=True,
        )
        user.set_password(password)
        user.save()

        role_objs = Role.objects.filter(name__in=roles)
        role_map = {r.name: r for r in role_objs}

        for role_name in roles:
            if role_name not in role_map:
                raise ValueError(f'Role not found in DB: {role_name}')
            UserRole.objects.create(
                user=user,
                role=role_map[role_name],
                assigned_by=created_by,
            )

        AuditLog.objects.create(
            user=created_by,
            action=AuditLog.CREATE,
            model_name='CustomUser',
            object_id=user.id,
            diff={
                'school_id': [None, school_id],
                'roles': [None, roles],
            },
            ip_address=ip_address,
        )

        return user

    @staticmethod
    @transaction.atomic
    def reset_password_by_it(
        *,
        target_user: CustomUser,
        new_password: str,
        reset_by: CustomUser,
        reason: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """IT Support resets a user's password — re-triggers first-login flow."""
        target_user.set_password(new_password)
        target_user.must_change_password = True
        target_user.save(update_fields=['password', 'must_change_password'])
        target_user.invalidate_role_cache()

        AuditLog.objects.create(
            user=reset_by,
            action=AuditLog.RESET_PASSWORD,
            model_name='CustomUser',
            object_id=target_user.id,
            diff={'reason': reason},
            ip_address=ip_address,
        )
