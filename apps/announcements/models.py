import uuid

from django.db import models


class Announcement(models.Model):
    ALL = 'ALL'
    ALL_STUDENTS = 'ALL_STUDENTS'
    ALL_TEACHERS = 'ALL_TEACHERS'
    BY_PROGRAM = 'BY_PROGRAM'
    BY_LEVEL = 'BY_LEVEL'
    PRINCIPAL = 'PRINCIPAL'
    SPECIFIC_USERS = 'SPECIFIC_USERS'

    RECIPIENT_TYPE_CHOICES = [
        (ALL, 'All Users'),
        (ALL_STUDENTS, 'All Students'),
        (ALL_TEACHERS, 'All Teachers'),
        (BY_PROGRAM, 'By Program'),
        (BY_LEVEL, 'By Level'),
        (PRINCIPAL, 'Principal'),
        (SPECIFIC_USERS, 'Specific Users'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    body = models.TextField()
    created_by = models.ForeignKey(
        'users.CustomUser', on_delete=models.CASCADE, related_name='announcements'
    )
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_TYPE_CHOICES)
    program = models.ForeignKey(
        'academics.Program', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='announcements',
    )
    level = models.ForeignKey(
        'academics.Level', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='announcements',
    )
    specific_users = models.ManyToManyField(
        'users.CustomUser', blank=True, related_name='specific_announcements'
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AnnouncementRecipient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name='recipients'
    )
    user = models.ForeignKey(
        'users.CustomUser', on_delete=models.CASCADE, related_name='announcement_recipients'
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('announcement', 'user')]
        indexes = [models.Index(fields=['user', 'announcement'])]

    def __str__(self):
        return f'{self.user.school_id} — {self.announcement.title}'
