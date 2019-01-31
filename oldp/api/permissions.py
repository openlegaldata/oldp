from rest_framework import permissions


class OwnerPrivatePermission(permissions.BasePermission):
    """
    Write: Only staff or owner
    Read: not private or owner or staff
    """

    def has_permission(self, request, view):
        if request.method not in permissions.SAFE_METHODS and not request.user.is_authenticated:
            return False
        else:
            return True

    def has_object_permission(self, request, view, obj):
        # Read requests
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_authenticated:
                if request.user.is_staff:
                    return True
                else:
                    return obj.get_private() == False or obj.get_owner() == request.user
            else:
                return obj.get_private() == False
        else:
            # Write requests
            if request.user.is_authenticated:
                if request.user.is_staff:
                    return True
                else:
                    return obj.get_owner() == request.user
            else:
                return False

