from django.db import migrations


LEVELS = [
    (1, 'Level 1 / Form 1'),
    (2, 'Level 2 / Form 2'),
    (3, 'Level 3 / Form 3'),
]


def seed_levels(apps, schema_editor):
    Level = apps.get_model('academics', 'Level')
    for number, name in LEVELS:
        Level.objects.get_or_create(number=number, defaults={'name': name})


def unseed_levels(apps, schema_editor):
    Level = apps.get_model('academics', 'Level')
    Level.objects.filter(number__in=[n for n, _ in LEVELS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_levels, reverse_code=unseed_levels),
    ]
