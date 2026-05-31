from django.contrib import admin

from apps.assessments.models import (
    Assignment,
    AssignmentSubmission,
    Question,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    Resource,
    TeacherEvaluation,
)


class QuestionInline(admin.TabularInline):
    model = Question
    fields = ('order', 'question_type', 'marks', 'question_text')
    extra = 0


class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    fields = ('text', 'is_correct')
    extra = 0


class QuizAttemptInline(admin.TabularInline):
    model = QuizAttempt
    fields = ('student', 'attempt_number', 'status', 'score', 'started_at', 'submitted_at')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class QuizAnswerInline(admin.TabularInline):
    model = QuizAnswer
    fields = ('question', 'selected_choices', 'text_answer')
    autocomplete_fields = ('question', 'selected_choices')
    extra = 0


class AssignmentSubmissionInline(admin.TabularInline):
    model = AssignmentSubmission
    fields = ('student', 'status', 'marks_obtained', 'graded_by', 'submitted_at', 'graded_at')
    readonly_fields = ('submitted_at', 'graded_at')
    autocomplete_fields = ('student', 'graded_by')
    extra = 0


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'assignment', 'resource_type', 'uploaded_at')
    list_filter = ('resource_type', 'uploaded_at', 'assignment__term', 'assignment__course')
    search_fields = (
        'title',
        'url',
        'assignment__course__code',
        'assignment__course__name',
        'assignment__teacher__school_id',
    )
    autocomplete_fields = ('assignment',)
    list_select_related = ('assignment__course', 'assignment__teacher', 'assignment__term')
    date_hierarchy = 'uploaded_at'


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'assignment', 'status', 'total_marks', 'max_attempts', 'due_datetime', 'created_at')
    list_filter = ('status', 'due_datetime', 'assignment__term', 'assignment__course')
    search_fields = (
        'title',
        'assignment__course__code',
        'assignment__course__name',
        'assignment__teacher__school_id',
    )
    autocomplete_fields = ('assignment',)
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('assignment__course', 'assignment__teacher', 'assignment__term')
    inlines = (QuestionInline, QuizAttemptInline)
    date_hierarchy = 'created_at'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'order', 'question_type', 'marks', 'question_preview')
    list_filter = ('question_type', 'quiz__status')
    search_fields = ('question_text', 'quiz__title', 'quiz__assignment__course__code')
    autocomplete_fields = ('quiz',)
    list_select_related = ('quiz__assignment__course',)
    inlines = (QuestionChoiceInline,)

    @admin.display(description='Question')
    def question_preview(self, obj):
        return obj.question_text[:80]


@admin.register(QuestionChoice)
class QuestionChoiceAdmin(admin.ModelAdmin):
    list_display = ('question', 'choice_preview', 'is_correct')
    list_filter = ('is_correct', 'question__question_type')
    search_fields = ('text', 'question__question_text', 'question__quiz__title')
    autocomplete_fields = ('question',)
    list_select_related = ('question__quiz',)

    @admin.display(description='Choice')
    def choice_preview(self, obj):
        return obj.text[:80]


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'student', 'attempt_number', 'status', 'score', 'started_at', 'submitted_at')
    list_filter = ('status', 'quiz__status', 'started_at', 'submitted_at')
    search_fields = (
        'quiz__title',
        'student__school_id',
        'student__first_name',
        'student__last_name',
    )
    autocomplete_fields = ('quiz', 'student')
    readonly_fields = ('started_at',)
    list_select_related = ('quiz__assignment__course', 'student')
    inlines = (QuizAnswerInline,)
    date_hierarchy = 'started_at'


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'answer_preview')
    search_fields = (
        'attempt__quiz__title',
        'attempt__student__school_id',
        'question__question_text',
        'text_answer',
    )
    autocomplete_fields = ('attempt', 'question', 'selected_choices')
    list_select_related = ('attempt__quiz', 'attempt__student', 'question')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('selected_choices')

    @admin.display(description='Answer')
    def answer_preview(self, obj):
        if obj.text_answer:
            return obj.text_answer[:80]
        return ', '.join(choice.text[:30] for choice in obj.selected_choices.all())


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'assignment', 'status', 'submission_type', 'max_marks', 'due_datetime', 'created_at')
    list_filter = ('status', 'submission_type', 'due_datetime', 'assignment__term', 'assignment__course')
    search_fields = (
        'title',
        'description',
        'assignment__course__code',
        'assignment__course__name',
        'assignment__teacher__school_id',
    )
    autocomplete_fields = ('assignment',)
    readonly_fields = ('created_at',)
    list_select_related = ('assignment__course', 'assignment__teacher', 'assignment__term')
    inlines = (AssignmentSubmissionInline,)
    date_hierarchy = 'created_at'


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'marks_obtained', 'graded_by', 'submitted_at', 'graded_at')
    list_filter = ('status', 'submitted_at', 'graded_at')
    search_fields = (
        'assignment__title',
        'student__school_id',
        'student__first_name',
        'student__last_name',
        'graded_by__school_id',
    )
    autocomplete_fields = ('assignment', 'student', 'graded_by')
    readonly_fields = ('submitted_at', 'graded_at')
    list_select_related = ('assignment__assignment__course', 'student', 'graded_by')
    date_hierarchy = 'submitted_at'


@admin.register(TeacherEvaluation)
class TeacherEvaluationAdmin(admin.ModelAdmin):
    list_display = ('student', 'teacher', 'course', 'term', 'rating', 'submitted_at')
    list_filter = ('rating', 'course', 'term', 'submitted_at')
    search_fields = (
        'student__school_id',
        'student__first_name',
        'student__last_name',
        'teacher__school_id',
        'teacher__first_name',
        'teacher__last_name',
        'course__code',
        'course__name',
    )
    autocomplete_fields = ('student', 'teacher', 'course', 'term')
    readonly_fields = ('submitted_at',)
    list_select_related = ('student', 'teacher', 'course', 'term__academic_year')
    date_hierarchy = 'submitted_at'
