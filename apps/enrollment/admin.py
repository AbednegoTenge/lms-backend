from django.contrib import admin

from apps.enrollment.models import Enrollment, SchoolClass, StudentProfile


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'program', 'class_teacher', 'capacity', 'student_count', 'is_active')
    list_filter = ('is_active', 'level', 'program')
    search_fields = (
        'name',
        'level__name',
        'program__name',
        'program__code',
        'class_teacher__school_id',
        'class_teacher__first_name',
        'class_teacher__last_name',
    )
    autocomplete_fields = ('level', 'program', 'class_teacher')
    list_select_related = ('level', 'program', 'class_teacher')

    @admin.display(description='Students')
    def student_count(self, obj):
        return obj.student_profiles.count()


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'level', 'program', 'school_class', 'class_section', 'status', 'enrolled_date')
    list_filter = ('status', 'level', 'program', 'school_class', 'class_section', 'enrolled_date')
    search_fields = (
        'user__school_id',
        'user__first_name',
        'user__last_name',
        'program__name',
        'program__code',
        'school_class__name',
        'class_section',
    )
    autocomplete_fields = ('user', 'level', 'program', 'school_class')
    list_select_related = ('user', 'level', 'program', 'school_class')
    date_hierarchy = 'enrolled_date'


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'course',
        'term',
        'level',
        'enrollment_type',
        'is_active',
        'enrolled_by',
        'enrolled_at',
    )
    list_filter = ('enrollment_type', 'is_active', 'term', 'level', 'course__program')
    search_fields = (
        'student__school_id',
        'student__first_name',
        'student__last_name',
        'course__code',
        'course__name',
        'term__academic_year__name',
        'enrolled_by__school_id',
    )
    autocomplete_fields = ('student', 'course', 'term', 'level', 'enrolled_by')
    readonly_fields = ('enrolled_at',)
    list_select_related = ('student', 'course', 'term__academic_year', 'level', 'enrolled_by')
    date_hierarchy = 'enrolled_at'
