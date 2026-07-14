from apps.assessments.models import Quiz
from apps.enrollment.models import Enrollment


def is_enrolled(user, assignment):
    """assignment is a TeacherCourseAssignment."""
    return Enrollment.objects.filter(
        student=user,
        course=assignment.course,
        term=assignment.term,
        level=assignment.level,
        is_active=True,
    ).exists()


def can_view_resource(user, assignment):
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
        return True
    if user.has_role('TEACHER') and assignment.teacher_id == user.pk:
        return True
    if user.has_role('STUDENT'):
        return is_enrolled(user, assignment)
    return False


def can_upload_resource(user, assignment):
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN']):
        return True
    return user.has_role('TEACHER') and assignment.teacher_id == user.pk


def can_manage_quiz(user, quiz):
    """Teacher owns assignment, or admin/super_admin."""
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN']):
        return True
    return user.has_role('TEACHER') and quiz.assignment.teacher_id == user.pk


def can_view_quiz(user, quiz):
    """Admin/SuperAdmin/Principal always; teacher if own; student if enrolled and quiz OPEN."""
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
        return True
    if user.has_role('TEACHER') and quiz.assignment.teacher_id == user.pk:
        return True
    if user.has_role('STUDENT') and quiz.status == Quiz.OPEN:
        return is_enrolled(user, quiz.assignment)
    return False


def can_manage_assignment(user, course_assignment):
    """Teacher owns assignment, or Super Admin."""
    if user.has_role('SUPER_ADMIN'):
        return True
    return user.has_role('TEACHER') and course_assignment.teacher_id == user.pk


def can_view_assignment(user, course_assignment):
    """Admin/SuperAdmin/Principal always; teacher if own; student if enrolled."""
    if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
        return True
    if user.has_role('TEACHER') and course_assignment.teacher_id == user.pk:
        return True
    if user.has_role('STUDENT'):
        return is_enrolled(user, course_assignment)
    return False
