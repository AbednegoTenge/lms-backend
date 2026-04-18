from rest_framework import serializers

from apps.schedules.models import ClassTimetable, ExamSchedule, Holiday


class ClassTimetableSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    term_display = serializers.SerializerMethodField()
    day_display = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = ClassTimetable
        fields = [
            'id', 'course', 'course_name', 'teacher', 'teacher_name',
            'level', 'level_number', 'class_section', 'term', 'term_display',
            'day_of_week', 'day_display', 'start_time', 'end_time', 'room',
        ]
        read_only_fields = ['id']

    def get_teacher_name(self, obj):
        return f'{obj.teacher.first_name} {obj.teacher.last_name}'.strip()

    def get_term_display(self, obj):
        return f'Term {obj.term.term_number} {obj.term.academic_year.name}'


class ExamScheduleSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    term_display = serializers.SerializerMethodField()
    exam_type_display = serializers.CharField(source='get_exam_type_display', read_only=True)

    class Meta:
        model = ExamSchedule
        fields = [
            'id', 'course', 'course_name', 'level', 'level_number',
            'term', 'term_display', 'exam_date', 'start_time', 'end_time',
            'room', 'exam_type', 'exam_type_display',
        ]
        read_only_fields = ['id']

    def get_term_display(self, obj):
        return f'Term {obj.term.term_number} {obj.term.academic_year.name}'


class HolidaySerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = Holiday
        fields = ['id', 'name', 'start_date', 'end_date', 'academic_year', 'academic_year_name']
        read_only_fields = ['id']
