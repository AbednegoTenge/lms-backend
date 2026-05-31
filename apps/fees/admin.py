from django.contrib import admin

from apps.fees.models import AdditionalFee, FeeStructure, Payment, StudentFee


class PaymentInline(admin.TabularInline):
    model = Payment
    fields = ('amount', 'payment_method', 'reference', 'recorded_by', 'paid_at')
    autocomplete_fields = ('recorded_by',)
    extra = 0


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = (
        'level',
        'program',
        'term',
        'base_amount',
        'effective_from',
        'is_active',
        'created_by',
    )
    list_filter = ('is_active', 'level', 'program', 'term', 'effective_from')
    search_fields = (
        'description',
        'program__name',
        'program__code',
        'term__academic_year__name',
        'created_by__school_id',
    )
    autocomplete_fields = ('level', 'program', 'term', 'created_by')
    list_select_related = ('level', 'program', 'term__academic_year', 'created_by')
    date_hierarchy = 'effective_from'


@admin.register(AdditionalFee)
class AdditionalFeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'applies_to', 'program', 'level', 'term', 'is_active')
    list_filter = ('applies_to', 'is_active', 'program', 'level', 'term')
    search_fields = ('name', 'program__name', 'program__code', 'term__academic_year__name')
    autocomplete_fields = ('program', 'level', 'term')
    list_select_related = ('program', 'level', 'term__academic_year')


@admin.register(StudentFee)
class StudentFeeAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'term',
        'total_amount',
        'amount_paid',
        'balance',
        'payment_status',
        'generated_at',
    )
    list_filter = ('payment_status', 'term', 'generated_at')
    search_fields = (
        'student__school_id',
        'student__first_name',
        'student__last_name',
        'term__academic_year__name',
    )
    autocomplete_fields = ('student', 'term')
    readonly_fields = ('generated_at', 'updated_at', 'balance')
    list_select_related = ('student', 'term__academic_year')
    inlines = (PaymentInline,)
    date_hierarchy = 'generated_at'

    @admin.display(description='Balance')
    def balance(self, obj):
        return obj.total_amount - obj.amount_paid


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('student_fee', 'amount', 'payment_method', 'reference', 'recorded_by', 'paid_at')
    list_filter = ('payment_method', 'paid_at')
    search_fields = (
        'reference',
        'student_fee__student__school_id',
        'student_fee__student__first_name',
        'student_fee__student__last_name',
        'recorded_by__school_id',
    )
    autocomplete_fields = ('student_fee', 'recorded_by')
    list_select_related = ('student_fee__student', 'student_fee__term', 'recorded_by')
    date_hierarchy = 'paid_at'
