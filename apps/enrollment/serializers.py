from rest_framework import serializers

from apps.enrollment.models import Enrollment, StudentProfile


class StudentProfileSerializer(serializers.ModelSerializer):
    school_id = serializers.CharField(source='user.school_id', read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    must_change_password = serializers.BooleanField(source='user.must_change_password', read_only=True)
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    program_name = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            'id',
            'school_id',
            'full_name',
            'must_change_password',
            'level',
            'level_number',
            'program',
            'program_name',
            'class_section',
            'status',
            'enrolled_date',
        ]
        read_only_fields = ['id', 'school_id', 'full_name', 'must_change_password', 'level_number', 'program_name']

    def get_program_name(self, obj):
        if obj.program:
            return obj.program.get_name_display()
        return None


class StudentProfileCreateSerializer(serializers.ModelSerializer):
    """Used by POST /students/ — creates a CustomUser + StudentProfile together."""
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True, required=False, allow_null=True)
    phone = serializers.CharField(write_only=True, required=False, allow_null=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = StudentProfile
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'password',
            'level', 'program', 'class_section', 'enrolled_date',
        ]


class EnrollmentSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    course_type_display = serializers.CharField(source='course.get_course_type_display', read_only=True)
    term_display = serializers.SerializerMethodField()
    level_number = serializers.IntegerField(source='level.number', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id',
            'student',
            'course',
            'course_name',
            'course_code',
            'course_type_display',
            'term',
            'term_display',
            'level',
            'level_number',
            'enrollment_type',
            'enrolled_at',
            'is_active',
        ]
        read_only_fields = [
            'id', 'student', 'course_name', 'course_code', 'course_type_display',
            'term_display', 'level_number', 'enrolled_at',
        ]

    def get_term_display(self, obj):
        return str(obj.term)
