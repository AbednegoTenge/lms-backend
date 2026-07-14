from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
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
    Assignment,
    AssignmentSubmission,
    Question,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    Resource,
    TeacherEvaluation,
)
from apps.assessments.permissions import (
    can_manage_assignment,
    can_manage_quiz,
    can_upload_resource,
    can_view_assignment,
    can_view_quiz,
    can_view_resource,
    is_enrolled,
)
from apps.assessments.serializers import (
    AssignmentListSerializer,
    AssignmentSerializer,
    AssignmentSubmissionSerializer,
    GradeSubmissionSerializer,
    QuizAttemptSerializer,
    QuizListSerializer,
    QuizSerializer,
    QuizSubmitSerializer,
    ResourceSerializer,
    TeacherEvaluationSerializer,
    StudentAssignmentListSerializer,
)
from apps.assessments.services import validate_resource_file
from apps.enrollment.models import Enrollment
from apps.users.permissions import IsAdminOrPrincipalOrTeacher, IsStudent, IsTeacherOrStudentOrSuperAdmin


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

    def list(self, request, assignment_pk=None):
        assignment = self._get_assignment()
        if not can_view_resource(request.user, assignment):
            return _forbidden()
        qs = (
            Resource.objects
            .filter(assignment=assignment)
            .select_related('assignment__teacher')
        )
        return _ok(self.get_serializer(qs, many=True).data)

    def create(self, request, assignment_pk=None):
        assignment = self._get_assignment()
        if not can_upload_resource(request.user, assignment):
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
        if not can_upload_resource(request.user, assignment):
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

    serializer_class = QuizSerializer

    def get_permissions(self):
        # list: Admin/Principal/SuperAdmin/Teacher only (queryset differs per role inside view)
        if self.action == 'list':
            return [IsTeacherOrStudentOrSuperAdmin()]
        # start_attempt: students only
        if self.action == 'start_attempt':
            return [IsStudent()]
        # create/retrieve/partial_update/publish/submissions: any authenticated user;
        # object-level ownership enforced inside each action method
        return [IsAuthenticated()]

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
        if user.has_any_role('SUPER_ADMIN'):
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
        elif user.has_role('STUDENT'):
            # Must match a single Enrollment row on course+term+level+student —
            # three independent joins (one per field) would each be satisfiable
            # by a *different* enrollment, leaking visibility into quizzes the
            # student isn't actually enrolled in for that term/level.
            matching_enrollment = Enrollment.objects.filter(
                student=user,
                course=OuterRef('assignment__course'),
                term=OuterRef('assignment__term'),
                level=OuterRef('assignment__level'),
                is_active=True,
            )
            qs = Quiz.objects.filter(
                Exists(matching_enrollment)
            ).exclude(
                status=Quiz.DRAFT
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
        if not can_view_quiz(request.user, quiz):
            return _forbidden()
        return _ok(QuizSerializer(quiz).data)

    # ------------------------------------------------------------------
    # Partial update (DRAFT only)
    # ------------------------------------------------------------------
    def partial_update(self, request, pk=None):
        quiz = self._get_quiz(pk)
        if not can_manage_quiz(request.user, quiz):
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
        if not can_manage_quiz(request.user, quiz):
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

        if not is_enrolled(user, quiz.assignment):
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
            # Lock the quiz row so two concurrent start_attempt calls for the
            # same student can't both pass the max_attempts check before either
            # commits (previously caused an unhandled IntegrityError -> 500).
            quiz = Quiz.objects.select_for_update().get(pk=quiz.pk)

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

            try:
                with transaction.atomic():
                    attempt = QuizAttempt.objects.create(
                        quiz=quiz,
                        student=user,
                        attempt_number=attempts_count + 1,
                    )
            except IntegrityError:
                return _err(
                    'Attempt limit reached.',
                    status_code=status.HTTP_409_CONFLICT,
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

    def get_permissions(self):
        # submit is a student-only action; _get_attempt also filters by student=user
        return [IsStudent()]

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


def _get_course_assignment(pk):
    try:
        return (
            TeacherCourseAssignment.objects
            .select_related('teacher', 'course', 'term', 'level')
            .get(pk=pk)
        )
    except TeacherCourseAssignment.DoesNotExist:
        raise NotFound('Assignment not found.')


# ---------------------------------------------------------------------------
# CourseAssignmentViewSet
# ---------------------------------------------------------------------------

class CourseAssignmentViewSet(viewsets.GenericViewSet):
    """
    GET    /api/v1/course-assignments/                list
    POST   /api/v1/course-assignments/                create
    GET    /api/v1/course-assignments/{id}/           retrieve
    PATCH  /api/v1/course-assignments/{id}/           update (DRAFT only)
    POST   /api/v1/course-assignments/{id}/publish/   publish
    POST   /api/v1/course-assignments/{id}/submit/    student submits
    GET    /api/v1/course-assignments/{id}/submissions/ list submissions
    """

    serializer_class = AssignmentSerializer

    def get_permissions(self):
        # submit: students only
        if self.action == 'submit':
            return [IsStudent()]
        # list: all roles may call it; queryset is role-filtered inside the method
        # create/retrieve/partial_update/publish/submissions: authenticated; object-level in method
        return [IsAuthenticated()]

    def _get_assignment(self, pk):
        try:
            return (
                Assignment.objects
                .select_related(
                    'assignment__teacher', 'assignment__course',
                    'assignment__term', 'assignment__level',
                )
                .get(pk=pk)
            )
        except Assignment.DoesNotExist:
            raise NotFound('Course assignment not found.')

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def list(self, request):
        user = request.user

        if user.has_any_role(['SUPER_ADMIN']):
            qs = Assignment.objects.select_related(
                'assignment__teacher',
                'assignment__course',
                'assignment__term',
                'assignment__level',
            )

            serializer_class = AssignmentListSerializer

        elif user.has_role('TEACHER'):
            qs = Assignment.objects.filter(
                assignment__teacher=user,
            ).select_related(
                'assignment__teacher',
                'assignment__course',
                'assignment__term',
                'assignment__level',
            )

            serializer_class = AssignmentListSerializer

        elif user.has_role('STUDENT'):
            enrolled_course_ids = Enrollment.objects.filter(
                student=user,
                is_active=True,
            ).values_list('course_id', flat=True)

            qs = Assignment.objects.filter(
                assignment__course_id__in=enrolled_course_ids,
                status=Assignment.OPEN,
            ).select_related(
                'assignment__teacher',
                'assignment__course',
                'assignment__term',
                'assignment__level',
            ).prefetch_related('submissions')

            serializer_class = StudentAssignmentListSerializer

        else:
            return _forbidden()

        course = request.query_params.get('course')
        if course:
            qs = qs.filter(assignment__course_id=course)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        serializer = serializer_class(
            qs,
            many=True,
            context={'request': request}
        )

        return _ok(serializer.data)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create(self, request):
        user = request.user
        course_assignment_id = request.data.get('assignment')
        if not course_assignment_id:
            return _err('assignment is required.')
        try:
            course_assignment = (
                TeacherCourseAssignment.objects
                .select_related('teacher', 'course', 'term', 'level')
                .get(pk=course_assignment_id)
            )
        except TeacherCourseAssignment.DoesNotExist:
            return _err('Assignment not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not can_manage_assignment(user, course_assignment):
            return _forbidden()

        serializer = AssignmentSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        obj = serializer.save(assignment=course_assignment)
        return _ok(
            AssignmentSerializer(obj).data, 'Assignment created.', status.HTTP_201_CREATED
        )

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------
    def retrieve(self, request, pk=None):
        obj = self._get_assignment(pk)
        if not can_view_assignment(request.user, obj.assignment):
            return _forbidden()
        return _ok(AssignmentSerializer(obj).data)

    # ------------------------------------------------------------------
    # Partial update (DRAFT only)
    # ------------------------------------------------------------------
    def partial_update(self, request, pk=None):
        obj = self._get_assignment(pk)
        if not can_manage_assignment(request.user, obj.assignment):
            return _forbidden()
        if obj.status != Assignment.DRAFT:
            return _err(
                'Only DRAFT assignments can be edited.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        serializer = AssignmentSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        serializer.save()
        return _ok(serializer.data, 'Assignment updated.')

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        obj = self._get_assignment(pk)
        if not can_manage_assignment(request.user, obj.assignment):
            return _forbidden()
        if obj.status != Assignment.DRAFT:
            return _err(
                'Only DRAFT assignments can be published.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        obj.status = Assignment.OPEN
        obj.save(update_fields=['status'])
        return _ok(AssignmentSerializer(obj).data, 'Assignment published.')

    # ------------------------------------------------------------------
    # Submit (student)
    # ------------------------------------------------------------------
    @action(
        detail=True,
        methods=['post'],
        url_path='submit',
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[UploadThrottle],
    )
    def submit(self, request, pk=None):
        obj = self._get_assignment(pk)
        user = request.user

        if not is_enrolled(user, obj.assignment):
            return _forbidden('Not enrolled in this course.')
        if obj.status != Assignment.OPEN:
            return _err(
                'Assignment is not open for submissions.',
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Check duplicate submission
        if AssignmentSubmission.objects.filter(assignment=obj, student=user).exists():
            return _err(
                'You have already submitted this assignment.',
                status_code=status.HTTP_409_CONFLICT,
            )

        # Validate submission content per submission_type
        text_content = request.data.get('text_content')
        file = request.FILES.get('file')

        if obj.submission_type == Assignment.TEXT and not text_content:
            return _err('text_content is required for TEXT submissions.')
        if obj.submission_type == Assignment.DOCUMENT and not file:
            return _err('file is required for DOCUMENT submissions.')
        if obj.submission_type == Assignment.BOTH and not text_content and not file:
            return _err('Provide text_content, file, or both.')

        # Determine late status
        is_late = timezone.now() > obj.due_datetime
        sub_status = AssignmentSubmission.LATE if is_late else AssignmentSubmission.SUBMITTED

        # File validation
        if file:
            try:
                from apps.assessments.services import validate_resource_file
                validate_resource_file(file, 'OTHER')
            except DjangoValidationError as exc:
                return _err(exc.message)

        submission = AssignmentSubmission.objects.create(
            assignment=obj,
            student=user,
            text_content=text_content or None,
            file=file or None,
            status=sub_status,
        )
        return _ok(
            AssignmentSubmissionSerializer(submission).data,
            'Assignment submitted.',
            status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Submissions list
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'], url_path='submissions')
    def submissions(self, request, pk=None):
        obj = self._get_assignment(pk)
        user = request.user
        if not (user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']) or
                (user.has_role('TEACHER') and obj.assignment.teacher_id == user.pk)):
            return _forbidden()

        subs = (
            AssignmentSubmission.objects
            .filter(assignment=obj)
            .select_related('student', 'graded_by')
        )
        return _ok(AssignmentSubmissionSerializer(subs, many=True).data)


# ---------------------------------------------------------------------------
# AssignmentSubmissionViewSet  (grade endpoint)
# ---------------------------------------------------------------------------

class AssignmentSubmissionViewSet(viewsets.GenericViewSet):
    """
    PATCH /api/v1/assignment-submissions/{id}/grade/
    """

    def get_permissions(self):
        # grade: Super Admin or teacher who owns the course; enforced inside the action
        # Use IsAuthenticated here; the ownership check runs after the object is fetched
        return [IsAuthenticated()]

    def _get_submission(self, pk):
        try:
            return (
                AssignmentSubmission.objects
                .select_related(
                    'assignment__assignment__teacher',
                    'assignment__assignment__course',
                    'student',
                )
                .get(pk=pk)
            )
        except AssignmentSubmission.DoesNotExist:
            raise NotFound('Submission not found.')

    @action(detail=True, methods=['patch'], url_path='grade')
    def grade(self, request, pk=None):
        submission = self._get_submission(pk)
        course_assignment = submission.assignment.assignment
        user = request.user

        if not (user.has_role('SUPER_ADMIN') or
                (user.has_role('TEACHER') and course_assignment.teacher_id == user.pk)):
            return _forbidden()

        serializer = GradeSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        marks = serializer.validated_data['marks_obtained']
        if marks > submission.assignment.max_marks:
            return _err(
                f'marks_obtained cannot exceed max_marks ({submission.assignment.max_marks}).'
            )

        submission.marks_obtained = marks
        submission.feedback = serializer.validated_data.get('feedback', '')
        submission.graded_by = user
        submission.graded_at = timezone.now()
        submission.status = AssignmentSubmission.GRADED
        submission.save(update_fields=[
            'marks_obtained', 'feedback', 'graded_by', 'graded_at', 'status'
        ])
        return _ok(AssignmentSubmissionSerializer(submission).data, 'Submission graded.')


# ---------------------------------------------------------------------------
# TeacherEvaluationViewSet
# ---------------------------------------------------------------------------

class TeacherEvaluationViewSet(viewsets.GenericViewSet):
    """
    POST /api/v1/evaluations/   student submits evaluation
    GET  /api/v1/evaluations/   admin/principal see all; teacher sees own received
    """

    def get_permissions(self):
        # create: students only
        if self.action == 'create':
            return [IsStudent()]
        # list: Admin/Principal/SuperAdmin/Teacher (students are forbidden)
        return [IsAdminOrPrincipalOrTeacher()]

    def list(self, request):
        user = request.user
        # get_permissions() already blocks students; Admin/Principal/SuperAdmin see all,
        # Teachers see only evaluations they received.
        if user.has_role('TEACHER'):
            qs = TeacherEvaluation.objects.filter(
                teacher=user,
            ).select_related('student', 'teacher', 'course', 'term')
        else:
            qs = TeacherEvaluation.objects.select_related(
                'student', 'teacher', 'course', 'term'
            )
        return _ok(TeacherEvaluationSerializer(qs, many=True).data)

    def create(self, request):
        user = request.user
        serializer = TeacherEvaluationSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)

        teacher = serializer.validated_data['teacher']
        course = serializer.validated_data['course']
        term = serializer.validated_data['term']

        # Student must be enrolled in that course/term
        if not Enrollment.objects.filter(
            student=user, course=course, term=term, is_active=True,
        ).exists():
            return _forbidden('Not enrolled in this course for the given term.')

        # Teacher must be assigned to that course/term
        if not TeacherCourseAssignment.objects.filter(
            teacher=teacher, course=course, term=term, is_active=True,
        ).exists():
            return _err('Teacher is not assigned to this course for the given term.')

        try:
            evaluation = serializer.save(student=user)
        except Exception:
            return _err(
                'You have already submitted an evaluation for this teacher/course/term.',
                status_code=status.HTTP_409_CONFLICT,
            )

        return _ok(
            TeacherEvaluationSerializer(evaluation).data,
            'Evaluation submitted.',
            status.HTTP_201_CREATED,
        )
