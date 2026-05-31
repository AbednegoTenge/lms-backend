from django.contrib import admin

from apps.reports.models import ReportTask


@admin.register(ReportTask)
class ReportTaskAdmin(admin.ModelAdmin):
    list_display = (
        'report_type',
        'format',
        'status',
        'requested_by',
        'created_at',
        'completed_at',
    )
    list_filter = ('report_type', 'format', 'status', 'created_at', 'completed_at')
    search_fields = (
        'requested_by__school_id',
        'requested_by__first_name',
        'requested_by__last_name',
        'download_url',
        'error_message',
    )
    autocomplete_fields = ('requested_by',)
    readonly_fields = ('created_at', 'completed_at')
    list_select_related = ('requested_by',)
    date_hierarchy = 'created_at'
