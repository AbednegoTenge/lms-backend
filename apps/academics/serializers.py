from rest_framework import serializers

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


# ---------------------------------------------------------------------------
# AcademicYear
# ---------------------------------------------------------------------------

class AcademicYearSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AcademicYear
        fields = ['id', 'name', 'start_date', 'end_date', 'is_current', 'created_by', 'created_by_name']
        read_only_fields = ['id', 'created_by', 'created_by_name']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None

    def validate(self, attrs):
        start = attrs.get('start_date') or (self.instance.start_date if self.instance else None)
        end = attrs.get('end_date') or (self.instance.end_date if self.instance else None)
        if start and end and start >= end:
            raise serializers.ValidationError('start_date must be before end_date.')
        return attrs


# ---------------------------------------------------------------------------
# Term
# ---------------------------------------------------------------------------

class TermSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = Term
        fields = [
            'id', 'academic_year', 'academic_year_name',
            'term_number', 'start_date', 'end_date', 'is_current',
        ]
        read_only_fields = ['id', 'academic_year_name']

    def validate(self, attrs):
        start = attrs.get('start_date') or (self.instance.start_date if self.instance else None)
        end = attrs.get('end_date') or (self.instance.end_date if self.instance else None)
        if start and end and start >= end:
            raise serializers.ValidationError('start_date must be before end_date.')
        return attrs


# ---------------------------------------------------------------------------
# Level
# ---------------------------------------------------------------------------

class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = ['id', 'number', 'name']
        read_only_fields = ['id']


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

class ProgramSerializer(serializers.ModelSerializer):
    name_display = serializers.CharField(source='get_name_display', read_only=True)

    class Meta:
        model = Program
        fields = ['id', 'name', 'name_display', 'code']
        read_only_fields = ['id', 'name_display']


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

class CourseSerializer(serializers.ModelSerializer):
    program_name = serializers.SerializerMethodField()
    course_type_display = serializers.CharField(source='get_course_type_display', read_only=True)

    class Meta:
        model = Course
        fields = [
            'id', 'name', 'code', 'course_type', 'course_type_display',
            'program', 'program_name', 'is_active',
        ]
        read_only_fields = ['id', 'program_name', 'course_type_display']

    def get_program_name(self, obj):
        if obj.program:
            return obj.program.get_name_display()
        return None

    def validate(self, attrs):
        course_type = attrs.get('course_type') or (self.instance.course_type if self.instance else None)
        program = attrs.get('program') or (self.instance.program if self.instance else None)
        if course_type == 'CORE' and program is not None:
            raise serializers.ValidationError('CORE courses must not have a program.')
        if course_type == 'ELECTIVE' and program is None:
            raise serializers.ValidationError('ELECTIVE courses must have a program.')
        return attrs


# ---------------------------------------------------------------------------
# TeacherCourseAssignment
# ---------------------------------------------------------------------------

class TeacherCourseAssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    teacher_school_id = serializers.CharField(source='teacher.school_id', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    term_display = serializers.SerializerMethodField()
    level_name = serializers.CharField(source='level.name', read_only=True)
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TeacherCourseAssignment
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_school_id',
            'course', 'course_name', 'course_code',
            'term', 'term_display',
            'level', 'level_name',
            'is_active', 'assigned_by', 'assigned_by_name', 'assigned_at',
        ]
        read_only_fields = [
            'id', 'teacher_name', 'teacher_school_id', 'course_name', 'course_code',
            'term_display', 'level_name', 'assigned_by', 'assigned_by_name', 'assigned_at',
        ]

    def get_term_display(self, obj):
        return str(obj.term)

    def get_assigned_by_name(self, obj):
        if obj.assigned_by:
            return obj.assigned_by.get_full_name()
        return None


# ---------------------------------------------------------------------------
# WeeklyTopic
# ---------------------------------------------------------------------------

class WeeklyTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyTopic
        fields = ['id', 'week_number', 'title', 'description']
        read_only_fields = ['id']

    def validate_week_number(self, value):
        if not (1 <= value <= 14):
            raise serializers.ValidationError('week_number must be between 1 and 14.')
        return value


# ---------------------------------------------------------------------------
# CourseOutline (with nested WeeklyTopics)
# ---------------------------------------------------------------------------

class CourseOutlineSerializer(serializers.ModelSerializer):
    weekly_topics = WeeklyTopicSerializer(many=True)

    class Meta:
        model = CourseOutline
        fields = ['id', 'assignment', 'weekly_topics', 'created_at', 'updated_at']
        read_only_fields = ['id', 'assignment', 'created_at', 'updated_at']

    def validate_weekly_topics(self, value):
        week_numbers = [t['week_number'] for t in value]
        if len(week_numbers) != len(set(week_numbers)):
            raise serializers.ValidationError('Duplicate week_number values are not allowed.')
        return value

    def update(self, instance, validated_data):
        topics_data = validated_data.pop('weekly_topics', [])
        # Replace all weekly topics atomically
        instance.weekly_topics.all().delete()
        for topic in topics_data:
            WeeklyTopic.objects.create(outline=instance, **topic)
        instance.save()
        return instance
