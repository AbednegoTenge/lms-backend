import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.fees.models import FeeStructure, Payment, StudentFee
from apps.fees.serializers import FeeStructureSerializer, PaymentSerializer, StudentFeeSerializer
from apps.fees.tasks import send_fee_reminder
from apps.users.permissions import IsAdminOrPrincipal, IsAdminOrSuperAdmin, CanViewStudentFee


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


# ---------------------------------------------------------------------------
# FeeStructureViewSet
# ---------------------------------------------------------------------------

class FeeStructureViewSet(viewsets.GenericViewSet):
    """
    GET    /api/v1/fee-structures/         — list (Admin, Principal)
    POST   /api/v1/fee-structures/         — create (Admin)
    PATCH  /api/v1/fee-structures/{id}/    — update (Admin)
    DELETE /api/v1/fee-structures/{id}/    — delete (Admin)
    """

    serializer_class = FeeStructureSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['level', 'program', 'term', 'is_active']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'destroy'):
            return [IsAdminOrSuperAdmin()]
        return [IsAdminOrPrincipal()]

    def get_queryset(self):
        return (
            FeeStructure.objects
            .select_related('level', 'program', 'term__academic_year', 'created_by')
            .all()
        )

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save(created_by=request.user)
        return _ok(serializer.data, 'Fee structure created.', status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            instance = self.get_queryset().get(pk=pk)
        except FeeStructure.DoesNotExist:
            return _err('Fee structure not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(serializer.data, 'Fee structure updated.')

    def destroy(self, request, pk=None):
        try:
            instance = self.get_queryset().get(pk=pk)
        except FeeStructure.DoesNotExist:
            return _err('Fee structure not found.', status_code=status.HTTP_404_NOT_FOUND)
        instance.delete()
        return Response(
            {'success': True, 'message': 'Fee structure deleted.', 'data': {}},
            status=status.HTTP_204_NO_CONTENT,
        )


# ---------------------------------------------------------------------------
# StudentFee filter
# ---------------------------------------------------------------------------

class StudentFeeFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name='payment_status')
    level = django_filters.NumberFilter(
        field_name='student__student_profile__level__number'
    )

    class Meta:
        model = StudentFee
        fields = ['term', 'status', 'level']


# ---------------------------------------------------------------------------
# StudentFeeViewSet
# ---------------------------------------------------------------------------

class StudentFeeViewSet(viewsets.GenericViewSet):
    """
    GET    /api/v1/student-fees/               — list (Admin, Principal)
    GET    /api/v1/student-fees/{id}/          — retrieve (Admin, Principal, own Student)
    POST   /api/v1/student-fees/{id}/payments/ — record payment (Admin)
    POST   /api/v1/student-fees/send-reminder/ — enqueue reminder task (Admin)
    """

    serializer_class = StudentFeeSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StudentFeeFilter
    ordering_fields = ['generated_at', 'total_amount', 'payment_status']

    def get_permissions(self):
        if self.action == 'retrieve':
            return [CanViewStudentFee()]
        if self.action in ('payments', 'send_reminder'):
            return [IsAdminOrSuperAdmin()]
        return [IsAdminOrPrincipal()]

    def get_queryset(self):
        return (
            StudentFee.objects
            .select_related('student', 'term__academic_year')
            .prefetch_related('payments__recorded_by')
            .all()
        )

    def _get_student_fee(self, pk):
        try:
            return self.get_queryset().get(pk=pk)
        except StudentFee.DoesNotExist:
            return None

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response({'success': True, 'data': data})
        return _ok(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        student_fee = self._get_student_fee(pk)
        if student_fee is None:
            return _err('Student fee not found.', status_code=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, student_fee)
        return _ok(self.get_serializer(student_fee).data)

    @action(detail=True, methods=['post'], url_path='payments')
    def payments(self, request, pk=None):
        student_fee = self._get_student_fee(pk)
        if student_fee is None:
            return _err('Student fee not found.', status_code=status.HTTP_404_NOT_FOUND)

        required = ['amount', 'payment_method', 'paid_at']
        missing = [f for f in required if not request.data.get(f)]
        if missing:
            return _err('Missing required fields.', {f: ['This field is required.'] for f in missing})

        serializer = PaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        serializer.save(student_fee=student_fee, recorded_by=request.user)
        # Signal on Payment.post_save updates StudentFee.amount_paid automatically
        student_fee.refresh_from_db()
        return _ok(
            {
                'payment': serializer.data,
                'new_status': student_fee.payment_status,
                'amount_paid': str(student_fee.amount_paid),
            },
            'Payment recorded.',
            status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'], url_path='send-reminder')
    def send_reminder(self, request):
        student_ids = request.data.get('student_ids', [])
        message = request.data.get('message', '')

        if not student_ids:
            return _err('student_ids is required.', {'student_ids': ['This field is required.']})
        if not message:
            return _err('message is required.', {'message': ['This field is required.']})

        send_fee_reminder.delay(student_ids=student_ids, message=message)
        return _ok(
            {'queued': len(student_ids)},
            f'Fee reminder queued for {len(student_ids)} student(s).',
        )
