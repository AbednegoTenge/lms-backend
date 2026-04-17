from rest_framework import serializers

from apps.assessments.models import Resource


class ResourceSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Resource
        fields = ['id', 'title', 'resource_type', 'url', 'file', 'file_url', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at', 'file_url']
        extra_kwargs = {
            'file': {'write_only': True, 'required': False},
            'url': {'required': False},
        }

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def validate(self, attrs):
        resource_type = attrs.get('resource_type')
        url = attrs.get('url')
        file = attrs.get('file')

        if resource_type == Resource.VIDEO_LINK:
            if not url:
                raise serializers.ValidationError({'url': 'URL is required for VIDEO_LINK resources.'})
            if file:
                raise serializers.ValidationError({'file': 'File upload not allowed for VIDEO_LINK resources.'})
        else:
            if not file:
                raise serializers.ValidationError(
                    {'file': f'File upload is required for {resource_type} resources.'}
                )

        return attrs
