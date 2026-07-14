from rest_framework.permissions import BasePermission


class CanCreateAnnouncement(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_any_role(
            ['ADMIN', 'PRINCIPAL', 'IT_SUPPORT', 'SUPER_ADMIN']
        )


class IsCreatorOfAnnouncement(BasePermission):
    """View-level: authenticated. Object-level: must be creator."""

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return str(obj.created_by_id) == str(request.user.pk)
