from django.db import migrations


PROGRAMS = [
    ('GENERAL_ARTS', 'GA'),
    ('GENERAL_SCIENCE', 'GS'),
    ('HOME_ECONOMICS', 'HE'),
    ('BUSINESS', 'BUS'),
    ('VISUAL_ARTS', 'VA'),
]


def seed_programs(apps, schema_editor):
    Program = apps.get_model('academics', 'Program')
    for name, code in PROGRAMS:
        Program.objects.get_or_create(name=name, defaults={'code': code})


def unseed_programs(apps, schema_editor):
    Program = apps.get_model('academics', 'Program')
    Program.objects.filter(name__in=[n for n, _ in PROGRAMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0002_seed_levels'),
    ]

    operations = [
        migrations.RunPython(seed_programs, reverse_code=unseed_programs),
    ]
