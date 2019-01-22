from rest_framework import permissions


class OwnerPrivatePermission(permissions.BasePermission):
    """
    Write: Only staff or owner
    Read: not prive or owner or staff
    """

    def has_object_permission(self, request, view, obj):
        # Read requests
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_authenticated:
                if request.user.is_staff:
                    return True
                else:
                    return obj.private == False or obj.owner == request.user
            else:
                return obj.private == False
        else:
            # Write requests
            if request.user.is_authenticated:
                if request.user.is_staff:
                    return True
                else:
                    return obj.owner == request.user
            else:
                return False

