from django.contrib import admin

from apps.it_support.models import PasswordResetRequest, SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'category',
        'status',
        'priority',
        'raised_by',
        'assigned_to',
        'created_at',
        'resolved_at',
    )
    list_filter = ('category', 'status', 'priority', 'created_at', 'resolved_at')
    search_fields = (
        'title',
        'description',
        'raised_by__school_id',
        'raised_by__first_name',
        'raised_by__last_name',
        'assigned_to__school_id',
        'assigned_to__first_name',
        'assigned_to__last_name',
    )
    autocomplete_fields = ('raised_by', 'assigned_to')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('raised_by', 'assigned_to')
    date_hierarchy = 'created_at'


@admin.register(PasswordResetRequest)
class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ('requested_for', 'reset_by', 'reset_at', 'reason_preview')
    list_filter = ('reset_at',)
    search_fields = (
        'requested_for__school_id',
        'requested_for__first_name',
        'requested_for__last_name',
        'reset_by__school_id',
        'reset_by__first_name',
        'reset_by__last_name',
        'reason',
    )
    autocomplete_fields = ('requested_for', 'reset_by')
    readonly_fields = ('new_password_hash', 'reset_at')
    list_select_related = ('requested_for', 'reset_by')
    date_hierarchy = 'reset_at'

    @admin.display(description='Reason')
    def reason_preview(self, obj):
        return (obj.reason or '')[:80]
