from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.announcements.models import Announcement, AnnouncementRecipient
from apps.announcements.permissions import CanCreateAnnouncement, IsCreatorOfAnnouncement
from apps.announcements.serializers import AnnouncementSerializer
from apps.announcements.tasks import fan_out_announcement


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


class AnnouncementViewSet(viewsets.GenericViewSet):
    serializer_class = AnnouncementSerializer
    filter_backends = [DjangoFilterBackend]

    def get_permissions(self):
        if self.action == 'create':
            return [CanCreateAnnouncement()]
        if self.action in ('partial_update', 'destroy', 'publish'):
            return [IsCreatorOfAnnouncement()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        return (
            Announcement.objects
            .filter(recipients__user=user)
            .select_related('created_by', 'program', 'level')
            .annotate(
                is_read=Subquery(
                    AnnouncementRecipient.objects.filter(
                        announcement=OuterRef('pk'),
                        user=user,
                    ).values('is_read')[:1]
                )
            )
            .distinct()
        )

    def list(self, request):
        qs = self.get_queryset()
        is_read_param = request.query_params.get('is_read')
        if is_read_param is not None:
            flag = is_read_param.lower() == 'true'
            qs = qs.filter(recipients__user=request.user, recipients__is_read=flag)
        return _ok(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except Announcement.DoesNotExist:
            return _err('Announcement not found.', status_code=status.HTTP_404_NOT_FOUND)
        return _ok(self.get_serializer(obj).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        obj = serializer.save(created_by=request.user)
        return _ok(self.get_serializer(obj).data, 'Announcement created.', status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            obj = Announcement.objects.get(pk=pk)
        except Announcement.DoesNotExist:
            return _err('Announcement not found.', status_code=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, obj)
        if obj.is_published:
            return _err('Cannot edit a published announcement.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(self.get_serializer(obj).data, 'Announcement updated.')

    def destroy(self, request, pk=None):
        try:
            obj = Announcement.objects.get(pk=pk)
        except Announcement.DoesNotExist:
            return _err('Announcement not found.', status_code=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, obj)
        if obj.is_published:
            return _err('Cannot delete a published announcement.', status_code=status.HTTP_403_FORBIDDEN)
        obj.delete()
        return Response({'success': True, 'message': 'Announcement deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        try:
            obj = Announcement.objects.get(pk=pk)
        except Announcement.DoesNotExist:
            return _err('Announcement not found.', status_code=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, obj)
        if obj.is_published:
            return _err('Announcement is already published.', status_code=status.HTTP_400_BAD_REQUEST)
        obj.is_published = True
        obj.published_at = timezone.now()
        obj.save(update_fields=['is_published', 'published_at'])
        fan_out_announcement.delay(str(obj.pk))
        return _ok({'id': str(obj.pk)}, 'Announcement published. Fan-out queued.')

    @action(detail=True, methods=['post'], url_path='read')
    def read(self, request, pk=None):
        try:
            recipient = AnnouncementRecipient.objects.get(
                announcement_id=pk, user=request.user
            )
        except AnnouncementRecipient.DoesNotExist:
            return _err('Announcement not found.', status_code=status.HTTP_404_NOT_FOUND)
        if not recipient.is_read:
            recipient.is_read = True
            recipient.read_at = timezone.now()
            recipient.save(update_fields=['is_read', 'read_at'])
        return _ok({'is_read': True, 'read_at': recipient.read_at})
