from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.schedules.models import ClassTimetable, ExamSchedule, Holiday
from apps.schedules.serializers import (
    ClassTimetableSerializer,
    ExamScheduleSerializer,
    HolidaySerializer,
)
from apps.schedules.services import TimetableService
from apps.users.permissions import IsAdminOrSuperAdmin


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


class ClassTimetableViewSet(viewsets.GenericViewSet):
    serializer_class = ClassTimetableSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['level', 'day_of_week', 'term']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'destroy'):
            return [IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            ClassTimetable.objects
            .select_related('course', 'teacher', 'level', 'term__academic_year')
            .all()
        )

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        return _ok(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except ClassTimetable.DoesNotExist:
            return _err('Timetable entry not found.', status_code=status.HTTP_404_NOT_FOUND)
        return _ok(self.get_serializer(obj).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        obj, conflict = TimetableService.create(serializer.validated_data)
        if conflict:
            return _err(
                f'Timetable conflict: {conflict} is already booked at that time.',
                status_code=status.HTTP_409_CONFLICT,
            )
        return _ok(self.get_serializer(obj).data, 'Timetable entry created.', status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except ClassTimetable.DoesNotExist:
            return _err('Timetable entry not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        updated, conflict = TimetableService.update(obj, serializer.validated_data)
        if conflict:
            return _err(
                f'Timetable conflict: {conflict} is already booked at that time.',
                status_code=status.HTTP_409_CONFLICT,
            )
        return _ok(self.get_serializer(updated).data, 'Timetable entry updated.')

    def destroy(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except ClassTimetable.DoesNotExist:
            return _err('Timetable entry not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response({'success': True, 'message': 'Timetable entry deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)


class ExamScheduleViewSet(viewsets.GenericViewSet):
    serializer_class = ExamScheduleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['level', 'term', 'exam_type']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'destroy'):
            return [IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            ExamSchedule.objects
            .select_related('course', 'level', 'term__academic_year')
            .all()
        )

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        return _ok(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except ExamSchedule.DoesNotExist:
            return _err('Exam schedule not found.', status_code=status.HTTP_404_NOT_FOUND)
        return _ok(self.get_serializer(obj).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        obj = serializer.save()
        return _ok(self.get_serializer(obj).data, 'Exam schedule created.', status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except ExamSchedule.DoesNotExist:
            return _err('Exam schedule not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(self.get_serializer(obj).data, 'Exam schedule updated.')

    def destroy(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except ExamSchedule.DoesNotExist:
            return _err('Exam schedule not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response({'success': True, 'message': 'Exam schedule deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)


class HolidayViewSet(viewsets.GenericViewSet):
    serializer_class = HolidaySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['academic_year']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'destroy'):
            return [IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Holiday.objects.select_related('academic_year').all()

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        return _ok(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except Holiday.DoesNotExist:
            return _err('Holiday not found.', status_code=status.HTTP_404_NOT_FOUND)
        return _ok(self.get_serializer(obj).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        obj = serializer.save()
        return _ok(self.get_serializer(obj).data, 'Holiday created.', status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except Holiday.DoesNotExist:
            return _err('Holiday not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(self.get_serializer(obj).data, 'Holiday updated.')

    def destroy(self, request, pk=None):
        try:
            obj = self.get_queryset().get(pk=pk)
        except Holiday.DoesNotExist:
            return _err('Holiday not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response({'success': True, 'message': 'Holiday deleted.', 'data': {}},
                        status=status.HTTP_204_NO_CONTENT)
