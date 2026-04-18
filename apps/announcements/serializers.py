from rest_framework import serializers

from apps.announcements.models import Announcement, AnnouncementRecipient


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    is_read = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'body', 'created_by', 'created_by_name',
            'recipient_type', 'program', 'level', 'is_published',
            'published_at', 'created_at', 'is_read',
        ]
        read_only_fields = ['id', 'created_by', 'published_at', 'created_at', 'is_read']

    def get_created_by_name(self, obj):
        return f'{obj.created_by.first_name} {obj.created_by.last_name}'.strip()


class AnnouncementRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnouncementRecipient
        fields = ['id', 'announcement', 'user', 'is_read', 'read_at']
        read_only_fields = ['id', 'announcement', 'user', 'read_at']
