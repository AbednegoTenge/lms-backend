import uuid

from django.db import models


class ReportTask(models.Model):
    ACADEMIC_PERFORMANCE = 'ACADEMIC_PERFORMANCE'
    FEE_COLLECTION = 'FEE_COLLECTION'
    TEACHER_EVALUATION = 'TEACHER_EVALUATION'
    REPORT_TYPE_CHOICES = [
        (ACADEMIC_PERFORMANCE, 'Academic Performance'),
        (FEE_COLLECTION, 'Fee Collection'),
        (TEACHER_EVALUATION, 'Teacher Evaluation'),
    ]

    CSV = 'CSV'
    PDF = 'PDF'
    FORMAT_CHOICES = [(CSV, 'CSV'), (PDF, 'PDF')]

    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    DONE = 'DONE'
    FAILED = 'FAILED'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (DONE, 'Done'),
        (FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='report_tasks',
    )
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES)
    filters = models.JSONField(default=dict)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=PENDING)
    download_url = models.CharField(max_length=2000, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'report_tasks'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.report_type} [{self.status}]'
