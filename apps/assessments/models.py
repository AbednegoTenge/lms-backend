import uuid

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
