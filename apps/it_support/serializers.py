from rest_framework import serializers

from apps.it_support.models import SupportTicket


class SupportTicketSerializer(serializers.ModelSerializer):
    raised_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'raised_by', 'raised_by_name', 'assigned_to', 'assigned_to_name',
            'title', 'description', 'category', 'status', 'priority',
            'created_at', 'updated_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'raised_by', 'created_at', 'updated_at']

    def get_raised_by_name(self, obj):
        return obj.raised_by.get_full_name() if obj.raised_by_id else None

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to_id else None


class SupportTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['title', 'description', 'category', 'priority']


class SupportTicketUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['status', 'assigned_to', 'priority', 'resolved_at']
