import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.academics.models import TeacherCourseAssignment


class Resource(models.Model):
    VIDEO_LINK = 'VIDEO_LINK'
    PDF = 'PDF'
    PRESENTATION = 'PRESENTATION'
    OTHER = 'OTHER'

    RESOURCE_TYPE_CHOICES = [
        (VIDEO_LINK, 'Video Link'),
        (PDF, 'PDF'),
        (PRESENTATION, 'Presentation'),
        (OTHER, 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        TeacherCourseAssignment,
        on_delete=models.CASCADE,
        related_name='resources',
    )
    title = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPE_CHOICES)
    url = models.URLField(null=True, blank=True)
    file = models.FileField(upload_to='resources/', null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'resources'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.title} ({self.resource_type})'


# ---------------------------------------------------------------------------
# Quiz lifecycle models
# ---------------------------------------------------------------------------

class Quiz(models.Model):
    DRAFT = 'DRAFT'
    OPEN = 'OPEN'
    CLOSED = 'CLOSED'
    STATUS_CHOICES = [
        (DRAFT, 'Draft'),
        (OPEN, 'Open'),
        (CLOSED, 'Closed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        TeacherCourseAssignment,
        on_delete=models.CASCADE,
        related_name='quizzes',
    )
    title = models.CharField(max_length=300)
    instructions = models.TextField(null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    due_datetime = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    total_marks = models.DecimalField(max_digits=6, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'quizzes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'due_datetime']),
        ]

    def __str__(self):
        return f'{self.title} [{self.status}]'


class Question(models.Model):
    MULTIPLE_CHOICE = 'MULTIPLE_CHOICE'
    MULTIPLE_ANSWER = 'MULTIPLE_ANSWER'
    TRUE_FALSE = 'TRUE_FALSE'
    SHORT_ANSWER = 'SHORT_ANSWER'
    QUESTION_TYPE_CHOICES = [
        (MULTIPLE_CHOICE, 'Multiple Choice'),
        (MULTIPLE_ANSWER, 'Multiple Answer'),
        (TRUE_FALSE, 'True/False'),
        (SHORT_ANSWER, 'Short Answer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    marks = models.DecimalField(max_digits=5, decimal_places=2)
    order = models.PositiveIntegerField()

    class Meta:
        db_table = 'questions'
        ordering = ['order']
        unique_together = [('quiz', 'order')]

    def __str__(self):
        return f'Q{self.order}: {self.question_text[:50]}'


class QuestionChoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    class Meta:
        db_table = 'question_choices'

    def __str__(self):
        return f'{self.text} ({"correct" if self.is_correct else "wrong"})'


class QuizAttempt(models.Model):
    IN_PROGRESS = 'IN_PROGRESS'
    SUBMITTED = 'SUBMITTED'
    GRADED = 'GRADED'
    STATUS_CHOICES = [
        (IN_PROGRESS, 'In Progress'),
        (SUBMITTED, 'Submitted'),
        (GRADED, 'Graded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    attempt_number = models.PositiveSmallIntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=IN_PROGRESS)

    class Meta:
        db_table = 'quiz_attempts'
        unique_together = [('quiz', 'student', 'attempt_number')]

    def __str__(self):
        return f'{self.student.school_id} — {self.quiz.title} attempt {self.attempt_number}'


class QuizAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    selected_choices = models.ManyToManyField(QuestionChoice, blank=True, related_name='answers')
    text_answer = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'quiz_answers'
        unique_together = [('attempt', 'question')]

    def __str__(self):
        return f'Answer to Q{self.question.order} in attempt {self.attempt.id}'
