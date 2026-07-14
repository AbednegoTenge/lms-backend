from rest_framework.permissions import BasePermission


class CanViewCourseOutline(BasePermission):
    """
    View-level: authenticated. Object-level: Admin/Principal/SuperAdmin always;
    Teacher who owns the assignment; any Student.
    obj is a CourseOutline (exposes assignment.teacher_id).
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.has_any_role(['ADMIN', 'SUPER_ADMIN', 'PRINCIPAL']):
            return True
        if user.has_role('TEACHER') and obj.assignment.teacher_id == user.id:
            return True
        return user.has_role('STUDENT')


class CanEditCourseOutline(BasePermission):
    """
    View-level: authenticated. Object-level: Admin/SuperAdmin always;
    Teacher only if they own the assignment.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.has_any_role(['ADMIN', 'SUPER_ADMIN']):
            return True
        return user.has_role('TEACHER') and obj.assignment.teacher_id == user.id
