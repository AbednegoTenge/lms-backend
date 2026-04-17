import uuid
from django.db import migrations


ROLES = [
    'STUDENT',
    'TEACHER',
    'ADMIN',
    'PRINCIPAL',
    'IT_SUPPORT',
    'SUPER_ADMIN',
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model('users', 'Role')
    for name in ROLES:
        Role.objects.get_or_create(name=name, defaults={'id': uuid.uuid4()})


def unseed_roles(apps, schema_editor):
    Role = apps.get_model('users', 'Role')
    Role.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_role_customuser_phone_customuser_profile_photo_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=unseed_roles),
    ]
