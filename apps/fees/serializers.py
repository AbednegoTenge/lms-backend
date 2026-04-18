from rest_framework import serializers

from apps.fees.models import FeeStructure, Payment, StudentFee


class FeeStructureSerializer(serializers.ModelSerializer):
    level_number = serializers.IntegerField(source='level.number', read_only=True)
    program_name = serializers.SerializerMethodField()
    term_display = serializers.SerializerMethodField()

    class Meta:
        model = FeeStructure
        fields = [
            'id', 'level', 'level_number', 'program', 'program_name',
            'term', 'term_display', 'base_amount', 'description',
            'effective_from', 'is_active', 'created_by',
        ]
        read_only_fields = ['id', 'created_by']

    def get_program_name(self, obj):
        return obj.program.get_name_display() if obj.program else None

    def get_term_display(self, obj):
        if obj.term:
            return f'Term {obj.term.term_number} {obj.term.academic_year.name}'
        return None


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'amount', 'payment_method', 'reference',
            'recorded_by', 'recorded_by_name', 'paid_at', 'notes',
        ]
        read_only_fields = ['id', 'recorded_by']

    def get_recorded_by_name(self, obj):
        if obj.recorded_by:
            return f'{obj.recorded_by.first_name} {obj.recorded_by.last_name}'.strip()
        return None


class StudentFeeSerializer(serializers.ModelSerializer):
    student_school_id = serializers.CharField(source='student.school_id', read_only=True)
    student_name = serializers.SerializerMethodField()
    term_display = serializers.SerializerMethodField()
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = StudentFee
        fields = [
            'id', 'student', 'student_school_id', 'student_name',
            'term', 'term_display', 'base_amount', 'additional_amount',
            'total_amount', 'amount_paid', 'payment_status',
            'generated_at', 'updated_at', 'payments',
        ]
        read_only_fields = [
            'id', 'student', 'student_school_id', 'student_name',
            'term_display', 'base_amount', 'additional_amount',
            'total_amount', 'amount_paid', 'payment_status',
            'generated_at', 'updated_at', 'payments',
        ]

    def get_student_name(self, obj):
        return f'{obj.student.first_name} {obj.student.last_name}'.strip()

    def get_term_display(self, obj):
        return f'Term {obj.term.term_number} {obj.term.academic_year.name}'
