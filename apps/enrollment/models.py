import uuid

from django.db import models

from apps.academics.models import Course, Level, Program, Term
from apps.users.models import CustomUser


class SchoolClass(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    level = models.ForeignKey(
        Level,
        on_delete=models.PROTECT,
        related_name='school_classes',
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='school_classes',
    )
    class_teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_classes',
    )
    capacity = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'school_classes'
        unique_together = [('name', 'level', 'program')]
        ordering = ['level__number', 'name']
        indexes = [
            models.Index(fields=['level', 'program', 'is_active']),
        ]

    def __str__(self):
        program = f' - {self.program.code}' if self.program else ''
        return f'{self.name} ({self.level.name}{program})'


class StudentProfile(models.Model):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'
    GRADUATED = 'GRADUATED'
    SUSPENDED = 'SUSPENDED'

    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (INACTIVE, 'Inactive'),
        (GRADUATED, 'Graduated'),
        (SUSPENDED, 'Suspended'),
    ]

    # Same UUID as the linked CustomUser
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='student_profile',
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.PROTECT,
        related_name='student_profiles',
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_profiles',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_profiles',
    )
    class_section = models.CharField(max_length=10, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    enrolled_date = models.DateField()

    class Meta:
        db_table = 'student_profiles'

    def __str__(self):
        return f'{self.user.school_id} — {self.user.get_full_name()}'


class Enrollment(models.Model):
    CORE = 'CORE'
    ELECTIVE = 'ELECTIVE'
    ENROLLMENT_TYPE_CHOICES = [(CORE, 'Core'), (ELECTIVE, 'Elective')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    enrollment_type = models.CharField(max_length=10, choices=ENROLLMENT_TYPE_CHOICES)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    enrolled_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_enrollments',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'enrollments'
        unique_together = [('student', 'course', 'term', 'level')]
        indexes = [
            models.Index(fields=['student', 'term']),
        ]

    def __str__(self):
        return f'{self.student.school_id} → {self.course.code} ({self.term})'
