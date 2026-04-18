import uuid

from django.db import models


class ClassTimetable(models.Model):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    DAY_CHOICES = [(MON, 'Monday'), (TUE, 'Tuesday'), (WED, 'Wednesday'),
                   (THU, 'Thursday'), (FRI, 'Friday')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey('academics.Course', on_delete=models.CASCADE, related_name='timetable_slots')
    teacher = models.ForeignKey('users.CustomUser', on_delete=models.CASCADE, related_name='timetable_slots')
    level = models.ForeignKey('academics.Level', on_delete=models.CASCADE, related_name='timetable_slots')
    class_section = models.CharField(max_length=10)
    term = models.ForeignKey('academics.Term', on_delete=models.CASCADE, related_name='timetable_slots')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50)

    class Meta:
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f'{self.course} — {self.get_day_of_week_display()} {self.start_time}'


class ExamSchedule(models.Model):
    MID_TERM = 'MID_TERM'
    END_OF_TERM = 'END_OF_TERM'
    EXAM_TYPE_CHOICES = [(MID_TERM, 'Mid Term'), (END_OF_TERM, 'End of Term')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey('academics.Course', on_delete=models.CASCADE, related_name='exam_schedules')
    level = models.ForeignKey('academics.Level', on_delete=models.CASCADE, related_name='exam_schedules')
    term = models.ForeignKey('academics.Term', on_delete=models.CASCADE, related_name='exam_schedules')
    exam_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES)

    class Meta:
        ordering = ['exam_date', 'start_time']

    def __str__(self):
        return f'{self.course} — {self.exam_type} — {self.exam_date}'


class Holiday(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    academic_year = models.ForeignKey(
        'academics.AcademicYear', on_delete=models.CASCADE, related_name='holidays'
    )

    class Meta:
        ordering = ['start_date']

    def __str__(self):
        return f'{self.name} ({self.start_date} – {self.end_date})'
