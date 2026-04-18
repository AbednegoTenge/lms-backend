import csv
import io
import logging

import boto3
from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _academic_rows(filters):
    from decimal import Decimal
    from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
    from apps.assessments.models import AssignmentSubmission, QuizAttempt

    quiz_qs = QuizAttempt.objects.filter(status=QuizAttempt.GRADED, score__isnull=False)
    asn_qs = AssignmentSubmission.objects.filter(
        status=AssignmentSubmission.GRADED, marks_obtained__isnull=False
    )
    if filters.get('term'):
        quiz_qs = quiz_qs.filter(quiz__assignment__term_id=filters['term'])
        asn_qs = asn_qs.filter(assignment__assignment__term_id=filters['term'])
    if filters.get('level'):
        quiz_qs = quiz_qs.filter(quiz__assignment__level__number=filters['level'])
        asn_qs = asn_qs.filter(assignment__assignment__level__number=filters['level'])
    if filters.get('program'):
        quiz_qs = quiz_qs.filter(quiz__assignment__course__program_id=filters['program'])
        asn_qs = asn_qs.filter(assignment__assignment__course__program_id=filters['program'])
    if filters.get('course'):
        quiz_qs = quiz_qs.filter(quiz__assignment__course_id=filters['course'])
        asn_qs = asn_qs.filter(assignment__assignment__course_id=filters['course'])

    quiz_by_course = list(
        quiz_qs.values(
            course_id=F('quiz__assignment__course_id'),
            course_name=F('quiz__assignment__course__name'),
        ).annotate(
            avg_score=Avg(
                ExpressionWrapper(
                    F('score') * 100.0 / F('quiz__total_marks'),
                    output_field=FloatField(),
                )
            ),
            count=Count('id'),
        )
    )
    asn_by_course = list(
        asn_qs.values(
            course_id=F('assignment__assignment__course_id'),
            course_name=F('assignment__assignment__course__name'),
        ).annotate(
            avg_score=Avg(
                ExpressionWrapper(
                    F('marks_obtained') * 100.0 / F('assignment__max_marks'),
                    output_field=FloatField(),
                )
            ),
            count=Count('id'),
        )
    )

    breakdown = {}
    for item in quiz_by_course + asn_by_course:
        cid = str(item['course_id'])
        if cid not in breakdown:
            breakdown[cid] = {
                'course_name': item['course_name'],
                'avg_score': 0.0,
                'count': 0,
            }
        existing = breakdown[cid]
        total = existing['count'] + item['count']
        existing['avg_score'] = round(
            (existing['avg_score'] * existing['count'] + (item['avg_score'] or 0) * item['count']) / total,
            2,
        ) if total > 0 else 0.0
        existing['count'] = total

    rows = [['Course', 'Avg Score (%)', 'Assessment Count']]
    for data in breakdown.values():
        rows.append([data['course_name'], data['avg_score'], data['count']])
    return rows


def _fee_rows(filters):
    from django.db.models import Count, Sum
    from apps.fees.models import StudentFee

    qs = StudentFee.objects.all()
    if filters.get('term'):
        qs = qs.filter(term_id=filters['term'])
    if filters.get('status'):
        qs = qs.filter(payment_status=filters['status'])

    breakdown = list(
        qs.values('payment_status')
        .annotate(count=Count('id'), total=Sum('total_amount'), collected=Sum('amount_paid'))
    )
    rows = [['Status', 'Count', 'Total Expected', 'Total Collected']]
    for item in breakdown:
        rows.append([
            item['payment_status'],
            item['count'],
            str(item['total'] or 0),
            str(item['collected'] or 0),
        ])
    return rows


def _evaluation_rows(filters):
    from django.db.models import Avg, Count, F
    from apps.assessments.models import TeacherEvaluation

    qs = TeacherEvaluation.objects.all()
    if filters.get('term'):
        qs = qs.filter(term_id=filters['term'])
    if filters.get('course'):
        qs = qs.filter(course_id=filters['course'])
    if filters.get('teacher'):
        qs = qs.filter(teacher_id=filters['teacher'])

    by_teacher = list(
        qs.values(
            t_id=F('teacher_id'),
            t_name=F('teacher__first_name'),
        ).annotate(
            avg_rating=Avg('rating'),
            total=Count('id'),
        )
    )
    rows = [['Teacher', 'Avg Rating', 'Total Evaluations']]
    for item in by_teacher:
        rows.append([item['t_name'], round(item['avg_rating'] or 0, 2), item['total']])
    return rows


def _get_rows(report_type, filters):
    if report_type == 'ACADEMIC_PERFORMANCE':
        return _academic_rows(filters)
    if report_type == 'FEE_COLLECTION':
        return _fee_rows(filters)
    if report_type == 'TEACHER_EVALUATION':
        return _evaluation_rows(filters)
    return [['No data']]


@shared_task
def export_report_csv(task_id):
    from apps.reports.models import ReportTask

    try:
        task = ReportTask.objects.get(pk=task_id)
    except ReportTask.DoesNotExist:
        logger.warning('export_report_csv: task %s not found', task_id)
        return

    task.status = ReportTask.PROCESSING
    task.save(update_fields=['status'])

    try:
        rows = _get_rows(task.report_type, task.filters)

        output = io.StringIO()
        csv.writer(output).writerows(rows)
        csv_bytes = output.getvalue().encode('utf-8')

        key = f'sms-reports/{task_id}.csv'
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
            Body=csv_bytes,
            ContentType='text/csv',
        )
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key},
            ExpiresIn=86400,
        )

        task.status = ReportTask.DONE
        task.download_url = url
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'download_url', 'completed_at'])
        logger.info('export_report_csv: task %s done, url=%s', task_id, url)

    except Exception as exc:
        task.status = ReportTask.FAILED
        task.error_message = str(exc)
        task.save(update_fields=['status', 'error_message'])
        logger.error('export_report_csv: task %s failed: %s', task_id, exc)
