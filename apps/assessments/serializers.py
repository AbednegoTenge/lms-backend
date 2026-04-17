from rest_framework import serializers

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


class ResourceSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Resource
        fields = ['id', 'title', 'resource_type', 'url', 'file', 'file_url', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at', 'file_url']
        extra_kwargs = {
            'file': {'write_only': True, 'required': False},
            'url': {'required': False},
        }

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def validate(self, attrs):
        resource_type = attrs.get('resource_type')
        url = attrs.get('url')
        file = attrs.get('file')

        if resource_type == Resource.VIDEO_LINK:
            if not url:
                raise serializers.ValidationError({'url': 'URL is required for VIDEO_LINK resources.'})
            if file:
                raise serializers.ValidationError({'file': 'File upload not allowed for VIDEO_LINK resources.'})
        else:
            if not file:
                raise serializers.ValidationError(
                    {'file': f'File upload is required for {resource_type} resources.'}
                )

        return attrs


# ---------------------------------------------------------------------------
# Quiz serializers
# ---------------------------------------------------------------------------

class QuestionChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionChoice
        fields = ['id', 'text', 'is_correct']
        read_only_fields = ['id']


class QuestionSerializer(serializers.ModelSerializer):
    choices = QuestionChoiceSerializer(many=True)

    class Meta:
        model = Question
        fields = ['id', 'question_text', 'question_type', 'marks', 'order', 'choices']
        read_only_fields = ['id']

    def validate_choices(self, value):
        return value


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True)
    assignment_id = serializers.UUIDField(source='assignment.id', read_only=True)

    class Meta:
        model = Quiz
        fields = [
            'id', 'assignment_id', 'title', 'instructions',
            'max_attempts', 'due_datetime', 'status', 'total_marks',
            'questions', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'assignment_id', 'status', 'created_at', 'updated_at']

    def create(self, validated_data):
        questions_data = validated_data.pop('questions')
        quiz = Quiz.objects.create(**validated_data)
        for q_data in questions_data:
            choices_data = q_data.pop('choices', [])
            question = Question.objects.create(quiz=quiz, **q_data)
            for c_data in choices_data:
                QuestionChoice.objects.create(question=question, **c_data)
        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if questions_data is not None:
            instance.questions.all().delete()
            for q_data in questions_data:
                choices_data = q_data.pop('choices', [])
                question = Question.objects.create(quiz=instance, **q_data)
                for c_data in choices_data:
                    QuestionChoice.objects.create(question=question, **c_data)
        return instance


class QuizListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list endpoint — omits nested questions."""
    assignment_id = serializers.UUIDField(source='assignment.id', read_only=True)

    class Meta:
        model = Quiz
        fields = [
            'id', 'assignment_id', 'title', 'max_attempts',
            'due_datetime', 'status', 'total_marks', 'created_at',
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Quiz attempt / submission serializers
# ---------------------------------------------------------------------------

class QuizAnswerWriteSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_choice_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    text_answer = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class QuizSubmitSerializer(serializers.Serializer):
    answers = QuizAnswerWriteSerializer(many=True)


class QuizAnswerReadSerializer(serializers.ModelSerializer):
    question_id = serializers.UUIDField(source='question.id', read_only=True)
    selected_choice_ids = serializers.SerializerMethodField()

    class Meta:
        model = QuizAnswer
        fields = ['id', 'question_id', 'selected_choice_ids', 'text_answer']

    def get_selected_choice_ids(self, obj):
        return list(obj.selected_choices.values_list('id', flat=True))


class QuizAttemptSerializer(serializers.ModelSerializer):
    answers = QuizAnswerReadSerializer(many=True, read_only=True)
    student_school_id = serializers.CharField(source='student.school_id', read_only=True)

    class Meta:
        model = QuizAttempt
        fields = [
            'id', 'quiz', 'student_school_id', 'attempt_number',
            'started_at', 'submitted_at', 'score', 'status', 'answers',
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Assignment serializers
# ---------------------------------------------------------------------------

class AssignmentSerializer(serializers.ModelSerializer):
    assignment_id = serializers.UUIDField(source='assignment.id', read_only=True)
    course_name = serializers.CharField(source='assignment.course.name', read_only=True)

    class Meta:
        model = Assignment
        fields = [
            'id', 'assignment_id', 'course_name', 'title', 'description',
            'due_datetime', 'submission_type', 'max_marks', 'status', 'created_at',
        ]
        read_only_fields = ['id', 'assignment_id', 'course_name', 'status', 'created_at']


class AssignmentListSerializer(serializers.ModelSerializer):
    assignment_id = serializers.UUIDField(source='assignment.id', read_only=True)
    course_name = serializers.CharField(source='assignment.course.name', read_only=True)

    class Meta:
        model = Assignment
        fields = [
            'id', 'assignment_id', 'course_name', 'title',
            'due_datetime', 'submission_type', 'max_marks', 'status', 'created_at',
        ]
        read_only_fields = ['id', 'assignment_id', 'course_name', 'status', 'created_at']


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    student_school_id = serializers.CharField(source='student.school_id', read_only=True)
    graded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentSubmission
        fields = [
            'id', 'assignment', 'student_school_id', 'submitted_at',
            'text_content', 'file', 'marks_obtained', 'feedback',
            'graded_by_name', 'graded_at', 'status',
        ]
        read_only_fields = [
            'id', 'assignment', 'student_school_id', 'submitted_at',
            'marks_obtained', 'feedback', 'graded_by_name', 'graded_at', 'status',
        ]
        extra_kwargs = {
            'file': {'write_only': True, 'required': False},
            'text_content': {'required': False},
        }

    def get_graded_by_name(self, obj):
        if obj.graded_by:
            return obj.graded_by.get_full_name()
        return None


class GradeSubmissionSerializer(serializers.Serializer):
    marks_obtained = serializers.DecimalField(max_digits=6, decimal_places=2)
    feedback = serializers.CharField(required=False, allow_blank=True)

    def validate_marks_obtained(self, value):
        if value < 0:
            raise serializers.ValidationError('marks_obtained cannot be negative.')
        return value


# ---------------------------------------------------------------------------
# Teacher Evaluation serializers
# ---------------------------------------------------------------------------

class TeacherEvaluationSerializer(serializers.ModelSerializer):
    student_school_id = serializers.CharField(source='student.school_id', read_only=True)
    teacher_school_id = serializers.CharField(source='teacher.school_id', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)

    class Meta:
        model = TeacherEvaluation
        fields = [
            'id', 'student_school_id', 'teacher', 'teacher_school_id',
            'course', 'course_code', 'term', 'rating', 'comment', 'submitted_at',
        ]
        read_only_fields = [
            'id', 'student_school_id', 'teacher_school_id', 'course_code', 'submitted_at',
        ]

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError('rating must be between 1 and 5.')
        return value
