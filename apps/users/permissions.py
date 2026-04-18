from rest_framework.permissions import BasePermission


# ---------------------------------------------------------------------------
# First-login guard
# ---------------------------------------------------------------------------

# Endpoints that a must-change-password user is still allowed to hit
EXEMPT_PATHS = {
    '/api/v1/auth/first-login-reset/',
    '/api/v1/auth/logout/',
}


class RequiresPasswordChange(BasePermission):
    """Block all requests when must_change_password=True, except exempt paths."""

    message = 'Password reset required before continuing.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return True  # unauthenticated requests handled by IsAuthenticated
        if not user.must_change_password:
            return True
        # Allow exempt paths
        path = request.path.rstrip('/')
        for exempt in EXEMPT_PATHS:
            if path == exempt.rstrip('/'):
                return True
        return False


# ---------------------------------------------------------------------------
# Role-based permissions
# ---------------------------------------------------------------------------

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role('ADMIN')


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role('SUPER_ADMIN')


class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_any_role(
            ['ADMIN', 'SUPER_ADMIN']
        )


class IsPrincipal(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role('PRINCIPAL')


class IsAdminOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_any_role(
            ['ADMIN', 'PRINCIPAL', 'SUPER_ADMIN']
        )


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role('TEACHER')


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role('STUDENT')


class IsITSupport(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role('IT_SUPPORT')


class IsITSupportOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_any_role(
            ['IT_SUPPORT', 'SUPER_ADMIN']
        )


class IsAdminOrPrincipalOrTeacher(BasePermission):
    """Admin / Principal / SuperAdmin / Teacher — for list endpoints with role-split querysets."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_any_role(
            ['ADMIN', 'PRINCIPAL', 'SUPER_ADMIN', 'TEACHER']
        )


class IsAdminOrPrincipalOrSelf(BasePermission):
    """
    View-level: any authenticated user may attempt the request.
    Object-level: Admin / Principal / SuperAdmin always; Student only for their own profile.
    obj must expose a ``user_id`` attribute (StudentProfile).
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.has_any_role(['ADMIN', 'PRINCIPAL', 'SUPER_ADMIN']):
            return True
        return user.has_role('STUDENT') and str(getattr(obj, 'user_id', None)) == str(user.pk)


class CanViewStudentCourses(BasePermission):
    """
    View-level: any authenticated user may attempt the request.
    Object-level: Admin / Principal / SuperAdmin / Teacher always; Student only for own profile.
    obj must expose a ``user_id`` attribute (StudentProfile).
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.has_any_role(['ADMIN', 'PRINCIPAL', 'SUPER_ADMIN', 'TEACHER']):
            return True
        return user.has_role('STUDENT') and str(getattr(obj, 'user_id', None)) == str(user.pk)


class CanViewStudentFee(BasePermission):
    """
    View-level: any authenticated user may attempt.
    Object-level: Admin / Principal / SuperAdmin always; Student only for own fee.
    obj must be a StudentFee instance (exposes student_id).
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.has_any_role(['ADMIN', 'PRINCIPAL', 'SUPER_ADMIN']):
            return True
        return user.has_role('STUDENT') and str(getattr(obj, 'student_id', None)) == str(user.pk)
