"""Custom permission classes for API token-based access control.

These permissions work with the fine-grained permission system to control
access to specific resources and actions based on the token's permission group.
"""

from rest_framework import permissions


class HasTokenPermission(permissions.BasePermission):
    """Permission class that checks if the authenticated token has permission
    for the requested resource and action.

    This permission class should be used on DRF viewsets to enforce
    fine-grained access control based on the token's permission group.

    Usage:
        class MyViewSet(viewsets.ModelViewSet):
            permission_classes = [HasTokenPermission]
            token_resource = 'cases'  # Define the resource name
    """

    def has_permission(self, request, view):
        """Check if the request has permission to access the view.

        Args:
            request: The DRF request object
            view: The DRF view object

        Returns:
            bool: True if the request is allowed, False otherwise
        """
        # Allow if not authenticated (other permission classes will handle this)
        if (
            not hasattr(request, "user")
            or not request.user
            or not request.user.is_authenticated
        ):
            return True

        # Allow superusers
        if request.user.is_superuser:
            return True

        # Determine the action based on the HTTP method
        action = self._get_action(request.method)

        # Requests not authenticated with an API token -- i.e. website session
        # auth or a legacy DRF Token -- cannot be evaluated against the
        # fine-grained token permission groups. Allow safe/read methods, but
        # require staff for writes so session auth cannot bypass the
        # deny-by-default write gating the token model enforces. Previously this
        # branch returned True unconditionally, which let any logged-in user
        # perform token-gated writes via the browsable API / session.
        from oldp.apps.accounts.models import APIToken

        if not isinstance(getattr(request, "auth", None), APIToken):
            if action == "read":
                return True
            return bool(request.user.is_staff)

        token = request.auth

        # Get the resource name from the view
        resource = self._get_resource(view)
        if not resource:
            # No resource specified, deny by default
            return False

        # Check if the token has the required permission
        return token.has_permission(resource, action)

    def _get_resource(self, view):
        """Extract the resource name from the view.

        The resource can be defined in multiple ways:
        1. view.token_resource attribute
        2. view.queryset.model._meta.model_name
        3. view.basename (for viewsets)

        Args:
            view: The DRF view object

        Returns:
            str: The resource name, or None if not found
        """
        # Check for explicit token_resource attribute
        if hasattr(view, "token_resource"):
            return view.token_resource

        # Try to get from queryset model
        if hasattr(view, "queryset") and view.queryset is not None:
            model_name = view.queryset.model._meta.model_name
            # Map model names to resource names
            resource_map = {
                "case": "cases",
                "law": "laws",
                "court": "courts",
                "lawbook": "lawbooks",
                "reference": "references",
                "annotation": "annotations",
            }
            return resource_map.get(model_name, model_name + "s")

        # Try to get from basename
        if hasattr(view, "basename"):
            return view.basename

        return None

    def _get_action(self, method):
        """Map HTTP methods to permission actions.

        Args:
            method: The HTTP method (GET, POST, PUT, PATCH, DELETE)

        Returns:
            str: The permission action ('read', 'write', 'delete')
        """
        safe_methods = ("GET", "HEAD", "OPTIONS")
        if method in safe_methods:
            return "read"
        elif method == "DELETE":
            return "delete"
        else:
            # POST, PUT, PATCH
            return "write"


class HasTokenResourcePermission(HasTokenPermission):
    """Object-level permission that checks token permissions for specific objects.

    This extends HasTokenPermission to add object-level checks.
    """

    def has_object_permission(self, request, view, obj):
        """Check if the request has permission to access the specific object.

        For now, this uses the same logic as has_permission(), but can be
        extended in the future to add object-specific checks.

        Args:
            request: The DRF request object
            view: The DRF view object
            obj: The object being accessed

        Returns:
            bool: True if the request is allowed, False otherwise
        """
        return self.has_permission(request, view)
