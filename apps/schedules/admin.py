from django.contrib import admin

from apps.schedules.models import ClassTimetable, ExamSchedule, Holiday


@admin.register(ClassTimetable)
class ClassTimetableAdmin(admin.ModelAdmin):
    list_display = (
        'course',
        'teacher',
        'level',
        'class_section',
        'term',
        'day_of_week',
        'start_time',
        'end_time',
        'room',
    )
    list_filter = ('day_of_week', 'term', 'level', 'course__program', 'class_section')
    search_fields = (
        'course__code',
        'course__name',
        'teacher__school_id',
        'teacher__first_name',
        'teacher__last_name',
        'class_section',
        'room',
    )
    autocomplete_fields = ('course', 'teacher', 'level', 'term')
    list_select_related = ('course', 'teacher', 'level', 'term__academic_year')
    ordering = ('day_of_week', 'start_time')


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ('course', 'level', 'term', 'exam_type', 'exam_date', 'start_time', 'end_time', 'room')
    list_filter = ('exam_type', 'exam_date', 'term', 'level', 'course__program')
    search_fields = ('course__code', 'course__name', 'room', 'term__academic_year__name')
    autocomplete_fields = ('course', 'level', 'term')
    list_select_related = ('course', 'level', 'term__academic_year')
    date_hierarchy = 'exam_date'
    ordering = ('exam_date', 'start_time')


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'start_date', 'end_date')
    list_filter = ('academic_year', 'start_date')
    search_fields = ('name', 'academic_year__name')
    autocomplete_fields = ('academic_year',)
    list_select_related = ('academic_year',)
    date_hierarchy = 'start_date'
