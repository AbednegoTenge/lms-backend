from django.db import migrations


CORE_COURSES = [
    ('Core Mathematics', 'CMATH'),
    ('Core English', 'CENG'),
    ('Core Physics', 'CPHY'),
    ('Core Biology', 'CBIO'),
    ('Core Chemistry', 'CCHEM'),
    ('Agriculture', 'AGRIC'),
    ('Social Studies', 'SOCST'),
]


def seed_core_courses(apps, schema_editor):
    Course = apps.get_model('academics', 'Course')
    for name, code in CORE_COURSES:
        Course.objects.get_or_create(
            code=code,
            defaults={'name': name, 'course_type': 'CORE', 'program': None, 'is_active': True},
        )


def unseed_core_courses(apps, schema_editor):
    Course = apps.get_model('academics', 'Course')
    Course.objects.filter(code__in=[c for _, c in CORE_COURSES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0003_seed_programs'),
    ]

    operations = [
        migrations.RunPython(seed_core_courses, reverse_code=unseed_core_courses),
    ]
