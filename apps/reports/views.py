from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q, Sum
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.reports.models import ReportTask
from apps.reports.serializers import ExportRequestSerializer, ReportTaskSerializer
from apps.reports.tasks import export_report_csv
from apps.users.permissions import IsAdminOrPrincipal


class ReportThrottle(UserRateThrottle):
    scope = 'report'

    def get_rate(self):
        try:
            return super().get_rate()
        except ImproperlyConfigured:
            return None


def _ok(data, message='', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'data': data, 'message': message}, status=status_code)


def _err(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': None, 'message': message, 'errors': errors or {}},
        status=status_code,
    )


# ---------------------------------------------------------------------------
# Shared queryset builders
# ---------------------------------------------------------------------------

def _quiz_qs(filters):
    from apps.assessments.models import QuizAttempt
    qs = QuizAttempt.objects.filter(status=QuizAttempt.GRADED, score__isnull=False)
    if filters.get('term'):
        qs = qs.filter(quiz__assignment__term_id=filters['term'])
    if filters.get('level'):
        qs = qs.filter(quiz__assignment__level__number=filters['level'])
    if filters.get('program'):
        qs = qs.filter(quiz__assignment__course__program_id=filters['program'])
    if filters.get('course'):
        qs = qs.filter(quiz__assignment__course_id=filters['course'])
    return qs


def _asn_qs(filters):
    from apps.assessments.models import AssignmentSubmission
    qs = AssignmentSubmission.objects.filter(
        status=AssignmentSubmission.GRADED, marks_obtained__isnull=False
    )
    if filters.get('term'):
        qs = qs.filter(assignment__assignment__term_id=filters['term'])
    if filters.get('level'):
        qs = qs.filter(assignment__assignment__level__number=filters['level'])
    if filters.get('program'):
        qs = qs.filter(assignment__assignment__course__program_id=filters['program'])
    if filters.get('course'):
        qs = qs.filter(assignment__assignment__course_id=filters['course'])
    return qs


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _academic_performance_data(filters):
    quiz_qs = _quiz_qs(filters)
    asn_qs = _asn_qs(filters)

    pct_expr_quiz = ExpressionWrapper(
        F('score') * 100.0 / F('quiz__total_marks'), output_field=FloatField()
    )
    pct_expr_asn = ExpressionWrapper(
        F('marks_obtained') * 100.0 / F('assignment__max_marks'), output_field=FloatField()
    )

    quiz_stats = quiz_qs.aggregate(
        avg=Avg(pct_expr_quiz),
        total=Count('id'),
        passed=Count('id', filter=Q(score__gte=F('quiz__total_marks') * Decimal('0.5'))),
    )
    asn_stats = asn_qs.aggregate(
        avg=Avg(pct_expr_asn),
        total=Count('id'),
        passed=Count(
            'id', filter=Q(marks_obtained__gte=F('assignment__max_marks') * Decimal('0.5'))
        ),
    )

    q_total = quiz_stats['total'] or 0
    a_total = asn_stats['total'] or 0
    grand_total = q_total + a_total
    grand_passed = (quiz_stats['passed'] or 0) + (asn_stats['passed'] or 0)

    if grand_total > 0:
        avg_score = round(
            ((quiz_stats['avg'] or 0.0) * q_total + (asn_stats['avg'] or 0.0) * a_total)
            / grand_total,
            2,
        )
        pass_rate = round(grand_passed / grand_total, 4)
    else:
        avg_score = 0.0
        pass_rate = 0.0

    quiz_students = set(quiz_qs.values_list('student_id', flat=True))
    asn_students = set(asn_qs.values_list('student_id', flat=True))
    total_students = len(quiz_students | asn_students)

    quiz_by_course = list(
        quiz_qs.values(
            course_id=F('quiz__assignment__course_id'),
            course_name=F('quiz__assignment__course__name'),
        ).annotate(avg_score=Avg(pct_expr_quiz), count=Count('id'))
    )
    asn_by_course = list(
        asn_qs.values(
            course_id=F('assignment__assignment__course_id'),
            course_name=F('assignment__assignment__course__name'),
        ).annotate(avg_score=Avg(pct_expr_asn), count=Count('id'))
    )

    breakdown = {}
    for item in quiz_by_course + asn_by_course:
        cid = str(item['course_id'])
        if cid not in breakdown:
            breakdown[cid] = {
                'course_id': cid,
                'course_name': item['course_name'],
                'avg_score': 0.0,
                'assessments': 0,
            }
        b = breakdown[cid]
        new_count = b['assessments'] + item['count']
        b['avg_score'] = round(
            (b['avg_score'] * b['assessments'] + (item['avg_score'] or 0.0) * item['count'])
            / new_count,
            2,
        ) if new_count > 0 else 0.0
        b['assessments'] = new_count

    return {
        'total_students': total_students,
        'avg_score': avg_score,
        'pass_rate': pass_rate,
        'course_breakdown': list(breakdown.values()),
    }


def _fee_collection_data(filters):
    from apps.fees.models import StudentFee

    qs = StudentFee.objects.all()
    if filters.get('term'):
        qs = qs.filter(term_id=filters['term'])
    if filters.get('status'):
        qs = qs.filter(payment_status=filters['status'])

    agg = qs.aggregate(total_expected=Sum('total_amount'), total_collected=Sum('amount_paid'))
    total_expected = agg['total_expected'] or Decimal('0.00')
    total_collected = agg['total_collected'] or Decimal('0.00')

    breakdown_qs = StudentFee.objects.all()
    if filters.get('term'):
        breakdown_qs = breakdown_qs.filter(term_id=filters['term'])

    breakdown = list(
        breakdown_qs.values('payment_status').annotate(
            count=Count('id'),
            total=Sum('total_amount'),
            collected=Sum('amount_paid'),
        )
    )

    return {
        'total_expected': str(total_expected),
        'total_collected': str(total_collected),
        'outstanding': str(total_expected - total_collected),
        'breakdown_by_status': {
            item['payment_status']: {
                'count': item['count'],
                'total': str(item['total'] or Decimal('0.00')),
                'collected': str(item['collected'] or Decimal('0.00')),
            }
            for item in breakdown
        },
    }


def _teacher_evaluation_data(filters):
    from apps.assessments.models import TeacherEvaluation

    qs = TeacherEvaluation.objects.all()
    if filters.get('term'):
        qs = qs.filter(term_id=filters['term'])
    if filters.get('course'):
        qs = qs.filter(course_id=filters['course'])
    if filters.get('teacher'):
        qs = qs.filter(teacher_id=filters['teacher'])

    by_teacher = list(
        qs.values(t_id=F('teacher_id'), t_name=F('teacher__first_name'))
        .annotate(avg_rating=Avg('rating'), total_evaluations=Count('id'))
    )
    course_breakdown = list(
        qs.values(c_id=F('course_id'), c_name=F('course__name'))
        .annotate(avg_rating=Avg('rating'), total_evaluations=Count('id'))
    )

    return {
        'by_teacher': [
            {
                'teacher_id': str(item['t_id']),
                'teacher_name': item['t_name'],
                'avg_rating': round(item['avg_rating'] or 0, 2),
                'total_evaluations': item['total_evaluations'],
            }
            for item in by_teacher
        ],
        'course_breakdown': [
            {
                'course_id': str(item['c_id']),
                'course_name': item['c_name'],
                'avg_rating': round(item['avg_rating'] or 0, 2),
                'total_evaluations': item['total_evaluations'],
            }
            for item in course_breakdown
        ],
    }


# ---------------------------------------------------------------------------
# ViewSet
# ---------------------------------------------------------------------------

class ReportViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdminOrPrincipal]
    serializer_class = ReportTaskSerializer

    def academic_performance(self, request):
        filters = {k: request.query_params.get(k) for k in ('term', 'level', 'program', 'course')}
        return _ok(_academic_performance_data(filters))

    def fee_collection(self, request):
        filters = {k: request.query_params.get(k) for k in ('term', 'status')}
        return _ok(_fee_collection_data(filters))

    def teacher_evaluations(self, request):
        filters = {k: request.query_params.get(k) for k in ('term', 'course', 'teacher')}
        return _ok(_teacher_evaluation_data(filters))

    def export(self, request):
        self.throttle_classes = [ReportThrottle]
        self.check_throttles(request)
        serializer = ExportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return _err('Validation error.', serializer.errors)
        task = ReportTask.objects.create(
            requested_by=request.user,
            report_type=serializer.validated_data['report_type'],
            format=serializer.validated_data['format'],
            filters=serializer.validated_data.get('filters', {}),
        )
        export_report_csv.delay(str(task.pk))
        return _ok({'task_id': str(task.pk)}, 'Export started.', status.HTTP_202_ACCEPTED)

    def export_status(self, request, pk=None):
        try:
            task = ReportTask.objects.get(pk=pk)
        except ReportTask.DoesNotExist:
            return _err('Report task not found.', status_code=status.HTTP_404_NOT_FOUND)
        if str(task.requested_by_id) != str(request.user.pk):
            return _err('Not found.', status_code=status.HTTP_403_FORBIDDEN)
        return _ok(ReportTaskSerializer(task).data)
