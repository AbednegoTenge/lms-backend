from rest_framework import serializers

from apps.enrollment.models import Enrollment, SchoolClass, StudentProfile
from apps.academics.models import TeacherCourseAssignment


class SchoolClassSerializer(serializers.ModelSerializer):
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    level_name = serializers.CharField(source='level.name', read_only=True)
    program_name = serializers.SerializerMethodField()
    class_teacher_name = serializers.SerializerMethodField()
    class_teacher_school_id = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = SchoolClass
        fields = [
            'id',
            'name',
            'level',
            'level_number',
            'level_name',
            'program',
            'program_name',
            'class_teacher',
            'class_teacher_name',
            'class_teacher_school_id',
            'capacity',
            'student_count',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'level_number',
            'level_name',
            'program_name',
            'class_teacher_name',
            'class_teacher_school_id',
            'student_count',
            'created_at',
            'updated_at',
        ]

    def get_program_name(self, obj):
        if obj.program:
            return obj.program.get_name_display()
        return None

    def get_student_count(self, obj):
        if hasattr(obj, 'student_count'):
            return obj.student_count
        return obj.student_profiles.count()

    def get_class_teacher_name(self, obj):
        if obj.class_teacher:
            return obj.class_teacher.get_full_name()
        return None

    def get_class_teacher_school_id(self, obj):
        if obj.class_teacher:
            return obj.class_teacher.school_id
        return None

    def validate_class_teacher(self, value):
        if value and not value.has_role('TEACHER'):
            raise serializers.ValidationError('Class teacher must have the TEACHER role.')
        return value


class StudentProfileSerializer(serializers.ModelSerializer):
    school_id = serializers.CharField(source='user.school_id', read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    must_change_password = serializers.BooleanField(source='user.must_change_password', read_only=True)
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    school_class_name = serializers.CharField(source='school_class.name', read_only=True)
    program_name = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            'id',
            'school_id',
            'full_name',
            'must_change_password',
            'level_number',
            'program_name',
            'school_class_name',
            'class_section',
            'status',
            'enrolled_date',
        ]
        read_only_fields = [
            'id',
            'school_id',
            'full_name',
            'must_change_password',
            'level_number',
            'program_name',
            'school_class_name',
        ]

    def get_program_name(self, obj):
        if obj.program:
            return obj.program.get_name_display()
        return None

    def validate(self, attrs):
        school_class = attrs.get('school_class', getattr(self.instance, 'school_class', None))
        level = attrs.get('level', getattr(self.instance, 'level', None))
        program = attrs.get('program', getattr(self.instance, 'program', None))

        if school_class:
            if level and school_class.level_id != level.id:
                raise serializers.ValidationError({
                    'school_class': 'Class level must match student level.'
                })
            if program and school_class.program_id and school_class.program_id != program.id:
                raise serializers.ValidationError({
                    'school_class': 'Class program must match student program.'
                })

        return attrs


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
            'level', 'program', 'school_class', 'class_section', 'enrolled_date',
        ]

class EnrollmentSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    course_type_display = serializers.CharField(source='course.get_course_type_display', read_only=True)
    term_display = serializers.SerializerMethodField()
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    teacher = serializers.SerializerMethodField()

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
            'teacher',
        ]
        read_only_fields = [
            'id', 'student', 'course_name', 'course_code', 'course_type_display',
            'term_display', 'level_number', 'enrolled_at', 'teacher',
        ]

    def get_term_display(self, obj):
        return str(obj.term)

    def get_teacher(self, obj):
        teacher_map = self.context.get('teacher_map')

        if teacher_map is not None:
            assignment = teacher_map.get(
                (obj.course_id, obj.term_id, obj.level_id, self.context.get('school_class_id'))
            )
        else:
            # Fallback for single-object serialization without context.
            school_class_id = self.context.get('school_class_id')
            assignment = (
                TeacherCourseAssignment.objects
                .filter(
                    course_id=obj.course_id,
                    term_id=obj.term_id,
                    level_id=obj.level_id,
                    school_class_id=school_class_id,
                    is_active=True,
                )
                .select_related('teacher')
                .first()
            )

        if assignment is None:
            return None

        return {
            'id': str(assignment.teacher.id),
            'school_id': assignment.teacher.school_id,
            'first_name': assignment.teacher.first_name,
            'last_name': assignment.teacher.last_name,
            'full_name': f'{assignment.teacher.first_name} {assignment.teacher.last_name}'.strip()
        }
