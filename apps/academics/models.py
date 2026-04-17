import uuid

from django.db import models

from apps.users.models import CustomUser


class AcademicYear(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20)          # e.g. "2024/2025"
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_academic_years',
    )

    class Meta:
        db_table = 'academic_years'
        ordering = ['-start_date']

    def save(self, *args, **kwargs):
        if self.is_current:
            # Enforce at most one current academic year
            AcademicYear.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Term(models.Model):
    TERM_CHOICES = [(1, 'Term 1'), (2, 'Term 2'), (3, 'Term 3')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='terms',
    )
    term_number = models.IntegerField(choices=TERM_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        db_table = 'terms'
        unique_together = [('academic_year', 'term_number')]
        ordering = ['academic_year__start_date', 'term_number']

    def __str__(self):
        return f'Term {self.term_number} — {self.academic_year.name}'


class Level(models.Model):
    LEVEL_CHOICES = [(1, 'Level 1'), (2, 'Level 2'), (3, 'Level 3')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.IntegerField(choices=LEVEL_CHOICES, unique=True)
    name = models.CharField(max_length=20)          # e.g. "Level 1 / Form 1"

    class Meta:
        db_table = 'levels'
        ordering = ['number']

    def __str__(self):
        return self.name


class Program(models.Model):
    GENERAL_ARTS = 'GENERAL_ARTS'
    GENERAL_SCIENCE = 'GENERAL_SCIENCE'
    HOME_ECONOMICS = 'HOME_ECONOMICS'
    BUSINESS = 'BUSINESS'
    VISUAL_ARTS = 'VISUAL_ARTS'

    PROGRAM_CHOICES = [
        (GENERAL_ARTS, 'General Arts'),
        (GENERAL_SCIENCE, 'General Science'),
        (HOME_ECONOMICS, 'Home Economics'),
        (BUSINESS, 'Business'),
        (VISUAL_ARTS, 'Visual Arts'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=PROGRAM_CHOICES, unique=True)
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        db_table = 'programs'
        ordering = ['name']

    def __str__(self):
        return self.get_name_display()


class Course(models.Model):
    CORE = 'CORE'
    ELECTIVE = 'ELECTIVE'
    COURSE_TYPE_CHOICES = [(CORE, 'Core'), (ELECTIVE, 'Elective')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    course_type = models.CharField(max_length=10, choices=COURSE_TYPE_CHOICES)
    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'courses'
        ordering = ['name']

    def __str__(self):
        return f'{self.code} — {self.name}'


class TeacherCourseAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='teaching_assignments',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='made_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teacher_course_assignments'
        unique_together = [('teacher', 'course', 'term', 'level')]

    def __str__(self):
        return f'{self.teacher.school_id} → {self.course.code} ({self.term})'


class CourseOutline(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.OneToOneField(
        TeacherCourseAssignment,
        on_delete=models.CASCADE,
        related_name='outline',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'course_outlines'

    def __str__(self):
        return f'Outline for {self.assignment}'


class WeeklyTopic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outline = models.ForeignKey(
        CourseOutline,
        on_delete=models.CASCADE,
        related_name='weekly_topics',
    )
    week_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()

    class Meta:
        db_table = 'weekly_topics'
        unique_together = [('outline', 'week_number')]
        ordering = ['week_number']

    def __str__(self):
        return f'Week {self.week_number}: {self.title}'
