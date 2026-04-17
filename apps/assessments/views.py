from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from apps.academics.models import TeacherCourseAssignment
from apps.assessments.models import (
    Question,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    Resource,
)
from apps.assessments.serializers import (
    QuizAttemptSerializer,
    QuizListSerializer,
    QuizSerializer,
    QuizSubmitSerializer,
    ResourceSerializer,
)
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


# ---------------------------------------------------------------------------
# Quiz helpers
# ---------------------------------------------------------------------------

def _is_enrolled(user, assignment):
    return Enrollment.objects.filter(
        student=user,
        course=assignment.course,
        term=assignment.term,
        level=assignment.level,
        is_active=True,
    ).exists()


def _can_manage_quiz(user, quiz):
    """Teacher owns assignment, or admin/super_admin."""
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN']):
        return True
    return user.has_role('TEACHER') and quiz.assignment.teacher_id == user.pk


def _can_view_quiz(user, quiz):
    """Admin/SuperAdmin/Principal always; teacher if own; student if enrolled and quiz OPEN."""
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
        return True
    if user.has_role('TEACHER') and quiz.assignment.teacher_id == user.pk:
        return True
    if user.has_role('STUDENT') and quiz.status == Quiz.OPEN:
        return _is_enrolled(user, quiz.assignment)
    return False


def _grade_attempt(attempt):
    """Auto-grade all answers in an attempt. SHORT_ANSWER left as None."""
    total_score = Decimal('0.00')
    has_ungraded = False

    answers = attempt.answers.prefetch_related(
        'selected_choices', 'question__choices'
    ).select_related('question')

    for answer in answers:
        question = answer.question
        q_type = question.question_type

        if q_type == Question.SHORT_ANSWER:
            has_ungraded = True
            continue

        correct_ids = set(
            question.choices.filter(is_correct=True).values_list('id', flat=True)
        )
        selected_ids = set(answer.selected_choices.values_list('id', flat=True))

        if q_type in (Question.MULTIPLE_CHOICE, Question.TRUE_FALSE):
            if selected_ids == correct_ids:
                total_score += question.marks
        elif q_type == Question.MULTIPLE_ANSWER:
            if selected_ids == correct_ids:
                total_score += question.marks

    attempt.score = total_score
    attempt.status = QuizAttempt.SUBMITTED if has_ungraded else QuizAttempt.GRADED
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=['score', 'status', 'submitted_at'])


# ---------------------------------------------------------------------------
# QuizViewSet
# ---------------------------------------------------------------------------

class QuizViewSet(viewsets.GenericViewSet):
    """
    GET    /api/v1/quizzes/                   list
    POST   /api/v1/quizzes/                   create
    GET    /api/v1/quizzes/{id}/              retrieve
    PATCH  /api/v1/quizzes/{id}/             update (DRAFT only)
    POST   /api/v1/quizzes/{id}/publish/      publish
    POST   /api/v1/quizzes/{id}/attempts/     start attempt
    POST   /api/v1/quiz-attempts/{id}/submit/ submit attempt
    GET    /api/v1/quizzes/{id}/submissions/  list submissions
    """

    permission_classes = [IsAuthenticated]
    serializer_class = QuizSerializer

    def _get_quiz(self, pk):
        try:
            return (
                Quiz.objects
                .select_related('assignment__teacher', 'assignment__course',
                                 'assignment__term', 'assignment__level')
                .get(pk=pk)
            )
        except Quiz.DoesNotExist:
            raise NotFound('Quiz not found.')

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def list(self, request):
        user = request.user
        if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
            qs = Quiz.objects.select_related(
                'assignment__teacher', 'assignment__course',
                'assignment__term', 'assignment__level',
            )
        elif user.has_role('TEACHER'):
            qs = Quiz.objects.filter(
                assignment__teacher=user,
            ).select_related(
                'assignment__teacher', 'assignment__course',
                'assignment__term', 'assignment__level',
            )
        else:
            return _forbidden()

        course = request.query_params.get('course')
        if course:
            qs = qs.filter(assignment__course_id=course)
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return _ok(QuizListSerializer(qs, many=True).data)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create(self, request):
        user = request.user
        assignment_id = request.data.get('assignment')
        if not assignment_id:
            return _err('assignment is required.')
        try:
            assignment = (
                TeacherCourseAssignment.objects
                .select_related('teacher', 'course', 'term', 'level')
                .get(pk=assignment_id)
            )
        except TeacherCourseAssignment.DoesNotExist:
            return _err('Assignment not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not (user.has_any_role(['ADMIN', 'SUPER_ADMIN']) or
                (user.has_role('TEACHER') and assignment.teacher_id == user.pk)):
            return _forbidden()

        serializer = QuizSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        quiz = serializer.save(assignment=assignment)
        return _ok(QuizSerializer(quiz).data, 'Quiz created.', status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------
    def retrieve(self, request, pk=None):
        quiz = self._get_quiz(pk)
        if not _can_view_quiz(request.user, quiz):
            return _forbidden()
        return _ok(QuizSerializer(quiz).data)

    # ------------------------------------------------------------------
    # Partial update (DRAFT only)
    # ------------------------------------------------------------------
    def partial_update(self, request, pk=None):
        quiz = self._get_quiz(pk)
        if not _can_manage_quiz(request.user, quiz):
            return _forbidden()
        if quiz.status != Quiz.DRAFT:
            return _err(
                'Only DRAFT quizzes can be edited.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        serializer = QuizSerializer(quiz, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(serializer.data, 'Quiz updated.')

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        quiz = self._get_quiz(pk)
        if not _can_manage_quiz(request.user, quiz):
            return _forbidden()
        if quiz.status != Quiz.DRAFT:
            return _err(
                'Only DRAFT quizzes can be published.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        quiz.status = Quiz.OPEN
        quiz.save(update_fields=['status'])
        return _ok(QuizSerializer(quiz).data, 'Quiz published.')

    # ------------------------------------------------------------------
    # Start attempt
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='attempts')
    def start_attempt(self, request, pk=None):
        quiz = self._get_quiz(pk)
        user = request.user

        if not user.has_role('STUDENT'):
            return _forbidden('Only students can attempt quizzes.')
        if not _is_enrolled(user, quiz.assignment):
            return _forbidden('Not enrolled in this course.')
        if quiz.status != Quiz.OPEN:
            return _err(
                'Quiz is not open.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if timezone.now() > quiz.due_datetime:
            return _err(
                'Quiz due date has passed.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        with transaction.atomic():
            attempts_count = QuizAttempt.objects.filter(
                quiz=quiz, student=user,
            ).exclude(status=QuizAttempt.IN_PROGRESS).count()

            if attempts_count >= quiz.max_attempts:
                return _err(
                    'Attempt limit reached.',
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            # Check if already IN_PROGRESS
            in_progress = QuizAttempt.objects.filter(
                quiz=quiz, student=user, status=QuizAttempt.IN_PROGRESS,
            ).first()
            if in_progress:
                return _ok(QuizAttemptSerializer(in_progress).data)

            attempt = QuizAttempt.objects.create(
                quiz=quiz,
                student=user,
                attempt_number=attempts_count + 1,
            )

        return _ok(
            QuizAttemptSerializer(attempt).data,
            'Attempt started.',
            status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Submissions list
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'], url_path='submissions')
    def submissions(self, request, pk=None):
        quiz = self._get_quiz(pk)
        user = request.user
        if not (user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']) or
                (user.has_role('TEACHER') and quiz.assignment.teacher_id == user.pk)):
            return _forbidden()

        attempts = (
            QuizAttempt.objects
            .filter(quiz=quiz)
            .exclude(status=QuizAttempt.IN_PROGRESS)
            .select_related('student')
            .prefetch_related('answers__selected_choices', 'answers__question')
        )
        return _ok(QuizAttemptSerializer(attempts, many=True).data)


# ---------------------------------------------------------------------------
# QuizAttemptViewSet  (submit endpoint)
# ---------------------------------------------------------------------------

class QuizAttemptViewSet(viewsets.GenericViewSet):
    """
    POST /api/v1/quiz-attempts/{id}/submit/
    """
    permission_classes = [IsAuthenticated]

    def _get_attempt(self, pk, user):
        try:
            return (
                QuizAttempt.objects
                .select_related('quiz__assignment__teacher',
                                 'quiz__assignment__course',
                                 'quiz__assignment__term',
                                 'quiz__assignment__level',
                                 'student')
                .get(pk=pk, student=user)
            )
        except QuizAttempt.DoesNotExist:
            raise NotFound('Attempt not found.')

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        attempt = self._get_attempt(pk, request.user)

        if attempt.status != QuizAttempt.IN_PROGRESS:
            return _err(
                'Attempt is not in progress.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        quiz = attempt.quiz
        if quiz.status != Quiz.OPEN:
            return _err(
                'Quiz is no longer open.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if timezone.now() > quiz.due_datetime:
            return _err(
                'Quiz due date has passed.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serializer = QuizSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        answers_data = serializer.validated_data['answers']

        # Build question lookup
        questions = {str(q.id): q for q in quiz.questions.prefetch_related('choices').all()}

        with transaction.atomic():
            for answer_data in answers_data:
                q_id = str(answer_data['question_id'])
                if q_id not in questions:
                    return _err(f'Question {q_id} does not belong to this quiz.')

                question = questions[q_id]
                quiz_answer, _ = QuizAnswer.objects.get_or_create(
                    attempt=attempt, question=question
                )

                selected_ids = answer_data.get('selected_choice_ids', [])
                if selected_ids:
                    valid_choices = QuestionChoice.objects.filter(
                        id__in=selected_ids, question=question
                    )
                    quiz_answer.selected_choices.set(valid_choices)

                text = answer_data.get('text_answer')
                if text is not None:
                    quiz_answer.text_answer = text
                    quiz_answer.save(update_fields=['text_answer'])

            _grade_attempt(attempt)

        attempt.refresh_from_db()
        return _ok(QuizAttemptSerializer(attempt).data, 'Attempt submitted.')
