from rest_framework import permissions


class OwnerPrivatePermission(permissions.BasePermission):
    """Write: Only staff or owner
    Read: not private or owner or staff
    """

    def has_permission(self, request, view):
        if (
            request.method not in permissions.SAFE_METHODS
            and not request.user.is_authenticated
        ):
            return False
        else:
            return True

    def _is_public(self, obj):
        """Check if an object is publicly visible.

        Supports models using review_status (Case, Law, ...) and models
        using a private boolean (AnnotationLabel).
        """
        if hasattr(obj, "review_status"):
            return obj.review_status == "accepted"
        if hasattr(obj, "private"):
            return not obj.private
        return True

    def has_object_permission(self, request, view, obj):
        # Read requests
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_authenticated:
                if request.user.is_staff:
                    return True
                else:
                    return self._is_public(obj) or obj.get_owner() == request.user
            else:
                return self._is_public(obj)
        else:
            # Write requests
            if request.user.is_authenticated:
                if request.user.is_staff:
                    return True
                else:
                    return obj.get_owner() == request.user
            else:
                return False
