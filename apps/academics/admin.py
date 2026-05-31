from django.contrib import admin

from apps.academics.models import (
    AcademicYear,
    Course,
    CourseOutline,
    Level,
    Program,
    TeacherCourseAssignment,
    Term,
    WeeklyTopic,
)
from apps.assessments.models import Assignment, Quiz, Resource


class TermInline(admin.TabularInline):
    model = Term
    fields = ('term_number', 'start_date', 'end_date', 'is_current')
    extra = 0


class CourseInline(admin.TabularInline):
    model = Course
    fields = ('code', 'name', 'course_type', 'is_active')
    extra = 0


class TeacherCourseAssignmentInline(admin.TabularInline):
    model = TeacherCourseAssignment
    fields = ('teacher', 'term', 'level', 'is_active', 'assigned_at')
    readonly_fields = ('assigned_at',)
    autocomplete_fields = ('teacher', 'term', 'level')
    extra = 0


class WeeklyTopicInline(admin.TabularInline):
    model = WeeklyTopic
    fields = ('week_number', 'title', 'description')
    extra = 0


class CourseOutlineInline(admin.StackedInline):
    model = CourseOutline
    fields = ('created_at', 'updated_at')
    readonly_fields = fields
    can_delete = False
    extra = 0
    max_num = 1

    def has_add_permission(self, request, obj=None):
        return False


class ResourceReadonlyInline(admin.TabularInline):
    model = Resource
    fields = ('title', 'resource_type', 'url', 'file', 'uploaded_at')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class QuizReadonlyInline(admin.TabularInline):
    model = Quiz
    fields = ('title', 'status', 'total_marks', 'max_attempts', 'due_datetime')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class AssignmentReadonlyInline(admin.TabularInline):
    model = Assignment
    fields = ('title', 'status', 'submission_type', 'max_marks', 'due_datetime')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_current', 'created_by')
    list_filter = ('is_current', 'start_date')
    search_fields = ('name', 'created_by__school_id', 'created_by__first_name', 'created_by__last_name')
    autocomplete_fields = ('created_by',)
    inlines = (TermInline,)
    date_hierarchy = 'start_date'


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('academic_year', 'term_number', 'start_date', 'end_date', 'is_current')
    list_filter = ('academic_year', 'term_number', 'is_current')
    search_fields = ('academic_year__name',)
    autocomplete_fields = ('academic_year',)
    list_select_related = ('academic_year',)
    date_hierarchy = 'start_date'


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('number', 'name')
    list_filter = ('number',)
    search_fields = ('name',)
    ordering = ('number',)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')
    inlines = (CourseInline,)
    ordering = ('name',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'course_type', 'program', 'is_active')
    list_filter = ('course_type', 'program', 'is_active')
    search_fields = ('code', 'name', 'program__name', 'program__code')
    autocomplete_fields = ('program',)
    list_select_related = ('program',)
    inlines = (TeacherCourseAssignmentInline,)


@admin.register(TeacherCourseAssignment)
class TeacherCourseAssignmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'course', 'term', 'level', 'is_active', 'assigned_by', 'assigned_at')
    list_filter = ('is_active', 'term', 'level', 'course__program')
    search_fields = (
        'teacher__school_id',
        'teacher__first_name',
        'teacher__last_name',
        'course__code',
        'course__name',
        'term__academic_year__name',
        'assigned_by__school_id',
    )
    autocomplete_fields = ('teacher', 'course', 'term', 'level', 'assigned_by')
    readonly_fields = ('assigned_at',)
    list_select_related = ('teacher', 'course', 'term__academic_year', 'level', 'assigned_by')
    inlines = (CourseOutlineInline, ResourceReadonlyInline, QuizReadonlyInline, AssignmentReadonlyInline)
    date_hierarchy = 'assigned_at'


@admin.register(CourseOutline)
class CourseOutlineAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'created_at', 'updated_at')
    search_fields = ('assignment__course__code', 'assignment__course__name', 'assignment__teacher__school_id')
    autocomplete_fields = ('assignment',)
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('assignment__course', 'assignment__teacher')
    inlines = (WeeklyTopicInline,)


@admin.register(WeeklyTopic)
class WeeklyTopicAdmin(admin.ModelAdmin):
    list_display = ('outline', 'week_number', 'title')
    list_filter = ('week_number',)
    search_fields = ('title', 'outline__assignment__course__code', 'outline__assignment__course__name')
    autocomplete_fields = ('outline',)
    list_select_related = ('outline__assignment__course',)
