from rest_framework import serializers

from apps.reports.models import ReportTask


class ReportTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportTask
        fields = [
            'id', 'report_type', 'format', 'filters', 'status',
            'download_url', 'error_message', 'created_at', 'completed_at',
        ]
        read_only_fields = fields


class ExportRequestSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(choices=ReportTask.REPORT_TYPE_CHOICES)
    format = serializers.ChoiceField(choices=ReportTask.FORMAT_CHOICES)
    filters = serializers.DictField(required=False, default=dict)
