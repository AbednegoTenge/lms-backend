from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from apps.academics.models import TeacherCourseAssignment
from apps.enrollment.models import Enrollment, StudentProfile
from apps.fees.models import StudentFee
from apps.users.models import AuditLog, CustomUser, Role, SchoolIDCounter, UserRole


class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = (
            'school_id',
            'email',
            'first_name',
            'last_name',
            'phone',
            'is_staff',
            'is_superuser',
            'is_active',
            'must_change_password',
        )

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Passwords do not match.')
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class CustomUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = CustomUser
        fields = '__all__'


class UserRoleInline(admin.TabularInline):
    model = UserRole
    fk_name = 'user'
    autocomplete_fields = ('role', 'assigned_by')
    readonly_fields = ('assigned_at',)
    extra = 0


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    autocomplete_fields = ('level', 'program')
    extra = 0
    max_num = 1


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    fk_name = 'student'
    fields = ('course', 'term', 'level', 'enrollment_type', 'is_active', 'enrolled_at')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class StudentFeeInline(admin.TabularInline):
    model = StudentFee
    fk_name = 'student'
    fields = ('term', 'total_amount', 'amount_paid', 'payment_status', 'generated_at')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class TeachingAssignmentInline(admin.TabularInline):
    model = TeacherCourseAssignment
    fk_name = 'teacher'
    fields = ('course', 'term', 'level', 'is_active', 'assigned_at')
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    model = CustomUser
    inlines = (
        UserRoleInline,
        StudentProfileInline,
        EnrollmentInline,
        StudentFeeInline,
        TeachingAssignmentInline,
    )
    list_display = (
        'school_id',
        'full_name',
        'email',
        'roles_display',
        'is_active',
        'is_staff',
        'must_change_password',
    )
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'must_change_password', 'userrole__role__name')
    search_fields = ('school_id', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('school_id',)
    readonly_fields = ('date_joined', 'last_login')
    filter_horizontal = ('groups', 'user_permissions')
    fieldsets = (
        (None, {'fields': ('school_id', 'password')}),
        ('Personal information', {'fields': ('first_name', 'last_name', 'email', 'phone', 'profile_photo')}),
        ('Status', {'fields': ('is_active', 'is_staff', 'is_superuser', 'must_change_password')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'school_id',
                'first_name',
                'last_name',
                'email',
                'phone',
                'password1',
                'password2',
                'is_active',
                'is_staff',
                'is_superuser',
                'must_change_password',
            ),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('userrole_set__role')

    @admin.display(description='Full name', ordering='first_name')
    def full_name(self, obj):
        return obj.get_full_name()

    @admin.display(description='Roles')
    def roles_display(self, obj):
        return ', '.join(role.role.name for role in obj.userrole_set.all() if role.is_active)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_by', 'assigned_at', 'is_active')
    list_filter = ('role', 'is_active', 'assigned_at')
    search_fields = ('user__school_id', 'user__first_name', 'user__last_name', 'role__name')
    autocomplete_fields = ('user', 'role', 'assigned_by')
    readonly_fields = ('assigned_at',)
    list_select_related = ('user', 'role', 'assigned_by')


@admin.register(SchoolIDCounter)
class SchoolIDCounterAdmin(admin.ModelAdmin):
    list_display = ('prefix', 'last_value')
    search_fields = ('prefix',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_id', 'user', 'ip_address', 'timestamp')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__school_id', 'user__first_name', 'user__last_name', 'model_name', 'object_id')
    autocomplete_fields = ('user',)
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'diff', 'ip_address', 'timestamp')
    list_select_related = ('user',)
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
