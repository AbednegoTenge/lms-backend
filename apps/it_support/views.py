from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.it_support.models import PasswordResetRequest, SupportTicket
from apps.it_support.serializers import (
    SupportTicketCreateSerializer,
    SupportTicketSerializer,
    SupportTicketUpdateSerializer,
)
from apps.users.permissions import IsITSupportOrSuperAdmin


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


class SupportTicketViewSet(viewsets.GenericViewSet):
    serializer_class = SupportTicketSerializer

    def get_permissions(self):
        if self.action == 'partial_update':
            return [IsITSupportOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = SupportTicket.objects.select_related('raised_by', 'assigned_to')
        if user.has_any_role(['IT_SUPPORT', 'SUPER_ADMIN']):
            return qs.all()
        return qs.filter(raised_by=user)

    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            data = SupportTicketSerializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(SupportTicketSerializer(qs, many=True).data)

    def create(self, request):
        serializer = SupportTicketCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        ticket = serializer.save(raised_by=request.user)
        return _ok(
            SupportTicketSerializer(ticket).data,
            'Support ticket created.',
            status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        qs = self.get_queryset()
        try:
            ticket = qs.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return _err('Ticket not found.', status_code=status.HTTP_404_NOT_FOUND)
        return _ok(SupportTicketSerializer(ticket).data)

    def partial_update(self, request, pk=None):
        try:
            ticket = SupportTicket.objects.select_related('raised_by', 'assigned_to').get(pk=pk)
        except SupportTicket.DoesNotExist:
            return _err('Ticket not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketUpdateSerializer(ticket, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        # Auto-set resolved_at when status → RESOLVED
        if serializer.validated_data.get('status') == SupportTicket.RESOLVED and not ticket.resolved_at:
            serializer.validated_data['resolved_at'] = timezone.now()
        serializer.save()
        ticket.refresh_from_db()
        return _ok(SupportTicketSerializer(ticket).data, 'Ticket updated.')


class PasswordResetViewSet(viewsets.GenericViewSet):
    permission_classes = [IsITSupportOrSuperAdmin]

    def reset_password(self, request):
        from apps.users.models import AuditLog, CustomUser

        user_id = request.data.get('user_id')
        new_password = request.data.get('new_password')
        reason = request.data.get('reason', '')

        if not user_id:
            return _err('user_id is required.', {'user_id': ['This field is required.']})
        if not new_password:
            return _err('new_password is required.', {'new_password': ['This field is required.']})

        try:
            target_user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return _err('User not found.', status_code=status.HTTP_404_NOT_FOUND)

        target_user.set_password(new_password)
        target_user.must_change_password = True
        target_user.save(update_fields=['password', 'must_change_password'])

        PasswordResetRequest.objects.create(
            requested_for=target_user,
            reset_by=request.user,
            new_password_hash=target_user.password,
            reason=reason,
        )

        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.RESET_PASSWORD,
            model_name='CustomUser',
            object_id=target_user.pk,
            diff={'must_change_password': [False, True]},
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        return _ok(
            {'school_id': target_user.school_id, 'must_change_password': True},
            'Password reset. User must set a new password on next login.',
        )
