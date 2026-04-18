import uuid

from django.db import models


class SupportTicket(models.Model):
    PASSWORD_RESET = 'PASSWORD_RESET'
    COURSE_ISSUE = 'COURSE_ISSUE'
    SYSTEM_BUG = 'SYSTEM_BUG'
    OTHER = 'OTHER'
    CATEGORY_CHOICES = [
        (PASSWORD_RESET, 'Password Reset'),
        (COURSE_ISSUE, 'Course Issue'),
        (SYSTEM_BUG, 'System Bug'),
        (OTHER, 'Other'),
    ]

    OPEN = 'OPEN'
    IN_PROGRESS = 'IN_PROGRESS'
    RESOLVED = 'RESOLVED'
    CLOSED = 'CLOSED'
    STATUS_CHOICES = [
        (OPEN, 'Open'),
        (IN_PROGRESS, 'In Progress'),
        (RESOLVED, 'Resolved'),
        (CLOSED, 'Closed'),
    ]

    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'
    PRIORITY_CHOICES = [
        (LOW, 'Low'),
        (MEDIUM, 'Medium'),
        (HIGH, 'High'),
        (CRITICAL, 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raised_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='raised_tickets',
    )
    assigned_to = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
    )
    title = models.CharField(max_length=300)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=MEDIUM)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'support_tickets'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.status}] {self.title}'


class PasswordResetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_for = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='password_reset_requests',
    )
    reset_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='performed_password_resets',
    )
    new_password_hash = models.CharField(max_length=255)
    reset_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'password_reset_requests'
        ordering = ['-reset_at']

    def __str__(self):
        return f'PasswordReset for {self.requested_for_id} by {self.reset_by_id}'
