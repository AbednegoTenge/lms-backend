from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.academics.models import TeacherCourseAssignment
from apps.assessments.models import Resource
from apps.assessments.serializers import ResourceSerializer
from apps.assessments.services import validate_resource_file
from apps.enrollment.models import Enrollment


class UploadThrottle(UserRateThrottle):
    scope = 'upload'

    def get_rate(self):
        try:
            return super().get_rate()
        except ImproperlyConfigured:
            return None  # no throttling when rate is not configured (e.g. in tests)


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


def _forbidden(message='Permission denied.'):
    return Response(
        {'success': False, 'data': None, 'message': message},
        status=status.HTTP_403_FORBIDDEN,
    )


class ResourceViewSet(viewsets.GenericViewSet):
    """
    Nested under TeacherCourseAssignment:
      GET    /api/v1/assignments/{assignment_pk}/resources/
      POST   /api/v1/assignments/{assignment_pk}/resources/
      DELETE /api/v1/assignments/{assignment_pk}/resources/{pk}/
    """

    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated]

    def _get_assignment(self):
        pk = self.kwargs.get('assignment_pk')
        try:
            return (
                TeacherCourseAssignment.objects
                .select_related('teacher', 'course', 'term', 'level')
                .get(pk=pk)
            )
        except TeacherCourseAssignment.DoesNotExist:
            raise NotFound('Assignment not found.')

    def _can_view(self, user, assignment):
        if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
            return True
        if user.has_role('TEACHER') and assignment.teacher_id == user.pk:
            return True
        if user.has_role('STUDENT'):
            return Enrollment.objects.filter(
                student=user,
                course=assignment.course,
                term=assignment.term,
                level=assignment.level,
                is_active=True,
            ).exists()
        return False

    def _can_upload(self, user, assignment):
        if user.has_any_role(['ADMIN', 'SUPER_ADMIN']):
            return True
        return user.has_role('TEACHER') and assignment.teacher_id == user.pk

    def list(self, request, assignment_pk=None):
        assignment = self._get_assignment()
        if not self._can_view(request.user, assignment):
            return _forbidden()
        qs = (
            Resource.objects
            .filter(assignment=assignment)
            .select_related('assignment__teacher')
        )
        return _ok(self.get_serializer(qs, many=True).data)

    def create(self, request, assignment_pk=None):
        assignment = self._get_assignment()
        if not self._can_upload(request.user, assignment):
            return _forbidden()

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        resource_type = serializer.validated_data.get('resource_type')
        file = serializer.validated_data.get('file')

        if file:
            try:
                validate_resource_file(file, resource_type)
            except DjangoValidationError as exc:
                return _err(exc.message, status_code=status.HTTP_400_BAD_REQUEST)

        serializer.save(assignment=assignment)
        return _ok(serializer.data, 'Resource uploaded.', status.HTTP_201_CREATED)

    def destroy(self, request, assignment_pk=None, pk=None):
        assignment = self._get_assignment()
        if not self._can_upload(request.user, assignment):
            return _forbidden()
        try:
            resource = Resource.objects.get(pk=pk, assignment=assignment)
        except Resource.DoesNotExist:
            raise NotFound('Resource not found.')
        resource.delete()
        return Response(
            {'success': True, 'message': 'Resource deleted.', 'data': {}},
            status=status.HTTP_204_NO_CONTENT,
        )

    def get_throttles(self):
        if getattr(self, 'action', None) == 'create':
            return [UploadThrottle()]
        return super().get_throttles()

    def get_parsers(self):
        if getattr(self, 'action', None) == 'create':
            return [MultiPartParser(), FormParser()]
        return super().get_parsers()
