"""Tests for the fine-grained API token permission system."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.accounts.permissions import HasTokenPermission


class APITokenPermissionModelTestCase(TestCase):
    """Test cases for APITokenPermission model"""

    def test_permission_creation(self):
        """Test creating a permission"""
        permission, _ = APITokenPermission.objects.get_or_create(
            resource="tests",
            action="read",
            defaults={"description": "Read access to tests"},
        )
        self.assertEqual(str(permission), "tests:read")
        self.assertEqual(permission.get_permission_string(), "tests:read")

    def test_permission_unique_constraint(self):
        """Test that resource+action combination is unique"""
        permission1, created1 = APITokenPermission.objects.get_or_create(
            resource="tests2", action="read"
        )
        self.assertTrue(created1)

        # Trying to create duplicate should not create a new record
        permission2, created2 = APITokenPermission.objects.get_or_create(
            resource="tests2", action="read"
        )
        self.assertFalse(created2)
        self.assertEqual(permission1.id, permission2.id)

    def test_permission_ordering(self):
        """Test that permissions are ordered by resource then action"""
        # Clear existing permissions for this test
        APITokenPermission.objects.filter(
            resource__in=["testlaws", "testcases"]
        ).delete()

        p1, _ = APITokenPermission.objects.get_or_create(
            resource="testlaws", action="write"
        )
        p2, _ = APITokenPermission.objects.get_or_create(
            resource="testcases", action="read"
        )
        p3, _ = APITokenPermission.objects.get_or_create(
            resource="testcases", action="write"
        )

        permissions = list(
            APITokenPermission.objects.filter(
                resource__in=["testlaws", "testcases"]
            ).order_by("resource", "action")
        )
        self.assertEqual(permissions[0], p2)  # testcases:read
        self.assertEqual(permissions[1], p3)  # testcases:write
        self.assertEqual(permissions[2], p1)  # testlaws:write


class APITokenPermissionGroupModelTestCase(TestCase):
    """Test cases for APITokenPermissionGroup model"""

    def setUp(self):
        self.read_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        self.write_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="write"
        )
        self.read_laws, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="read"
        )

    def test_permission_group_creation(self):
        """Test creating a permission group"""
        group = APITokenPermissionGroup.objects.create(
            name="test_group", description="Test group"
        )
        group.permissions.add(self.read_cases)

        self.assertEqual(str(group), "test_group")
        self.assertEqual(group.permissions.count(), 1)

    def test_permission_group_has_permission(self):
        """Test checking if a group has a permission"""
        group = APITokenPermissionGroup.objects.create(name="test_group")
        group.permissions.add(self.read_cases, self.read_laws)

        self.assertTrue(group.has_permission("cases", "read"))
        self.assertTrue(group.has_permission("laws", "read"))
        self.assertFalse(group.has_permission("cases", "write"))

    def test_permission_group_get_permission_list(self):
        """Test getting all permissions as a list"""
        group = APITokenPermissionGroup.objects.create(name="test_group")
        group.permissions.add(self.read_cases, self.read_laws)

        permissions = group.get_permission_list()
        self.assertEqual(len(permissions), 2)
        self.assertIn("cases:read", permissions)
        self.assertIn("laws:read", permissions)

    def test_default_group(self):
        """Test default group flag"""
        # Create a different test group (not "default" since migration creates that)
        group, _ = APITokenPermissionGroup.objects.get_or_create(
            name="test_default_flag", defaults={"is_default": False}
        )
        # Now set it as default
        group.is_default = True
        group.save()

        # Reload to verify
        group.refresh_from_db()
        self.assertTrue(group.is_default)


class APITokenPermissionIntegrationTestCase(TestCase):
    """Test cases for token permission integration"""

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "password")

        # Create permissions (get_or_create to avoid conflicts with migration data)
        self.read_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        self.write_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="write"
        )
        self.delete_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="delete"
        )
        self.read_laws, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="read"
        )

        # Create permission groups (get_or_create to avoid conflicts)
        self.read_only_group, created = APITokenPermissionGroup.objects.get_or_create(
            name="test_read_only", defaults={"description": "Read-only access"}
        )
        if created:
            self.read_only_group.permissions.add(self.read_cases, self.read_laws)

        self.full_cases_group, created = APITokenPermissionGroup.objects.get_or_create(
            name="test_full_cases", defaults={"description": "Full access to cases"}
        )
        if created:
            self.full_cases_group.permissions.add(
                self.read_cases, self.write_cases, self.delete_cases
            )

    def test_token_with_permission_group(self):
        """Test token with assigned permission group"""
        token = APIToken.objects.create(
            user=self.user, name="Test Token", permission_group=self.read_only_group
        )

        self.assertTrue(token.has_permission("cases", "read"))
        self.assertTrue(token.has_permission("laws", "read"))
        self.assertFalse(token.has_permission("cases", "write"))
        self.assertFalse(token.has_permission("cases", "delete"))

    def test_token_with_full_permission_group(self):
        """Test token with full access permission group"""
        token = APIToken.objects.create(
            user=self.user,
            name="Full Access Token",
            permission_group=self.full_cases_group,
        )

        self.assertTrue(token.has_permission("cases", "read"))
        self.assertTrue(token.has_permission("cases", "write"))
        self.assertTrue(token.has_permission("cases", "delete"))
        self.assertFalse(token.has_permission("laws", "read"))

    def test_token_without_permission_group(self):
        """Test token without permission group (legacy behavior)"""
        token = APIToken.objects.create(user=self.user, name="Legacy Token")

        # Without permission group and scopes, should have full access
        self.assertTrue(token.has_permission("cases", "read"))
        self.assertTrue(token.has_permission("cases", "write"))
        self.assertTrue(token.has_permission("laws", "read"))

    def test_token_with_legacy_scopes(self):
        """Test token with legacy scopes (backward compatibility)"""
        token = APIToken.objects.create(
            user=self.user,
            name="Legacy Scoped Token",
            scopes=["cases:read", "laws:read"],
        )

        self.assertTrue(token.has_permission("cases", "read"))
        self.assertTrue(token.has_permission("laws", "read"))
        self.assertFalse(token.has_permission("cases", "write"))

    def test_token_get_permissions(self):
        """Test getting all permissions for a token"""
        token = APIToken.objects.create(
            user=self.user, name="Test Token", permission_group=self.read_only_group
        )

        permissions = token.get_permissions()
        self.assertEqual(len(permissions), 2)
        self.assertIn("cases:read", permissions)
        self.assertIn("laws:read", permissions)


class HasTokenPermissionTestCase(TestCase):
    """Test cases for HasTokenPermission DRF permission class"""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.superuser = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )

        # Create permissions (get_or_create to avoid conflicts with migration data)
        self.read_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        self.write_cases, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="write"
        )

        # Create permission group (get_or_create to avoid conflicts)
        self.read_only_group, created = APITokenPermissionGroup.objects.get_or_create(
            name="test_read_only_drf",
            defaults={"description": "Read-only for DRF tests"},
        )
        if created:
            self.read_only_group.permissions.add(self.read_cases)

        # Create token
        self.token = APIToken.objects.create(
            user=self.user, name="Test Token", permission_group=self.read_only_group
        )

        self.permission = HasTokenPermission()

    def test_unauthenticated_request(self):
        """Test that unauthenticated requests are allowed (handled by other permissions)"""
        request = self.factory.get("/api/cases/")
        view = type("View", (), {"token_resource": "cases"})()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_superuser_always_allowed(self):
        """Test that superusers are always allowed"""
        request = self.factory.get("/api/cases/")
        request.user = self.superuser
        request.auth = self.token
        view = type("View", (), {"token_resource": "cases"})()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_token_with_read_permission_get_request(self):
        """Test token with read permission on GET request"""
        request = self.factory.get("/api/cases/")
        request.user = self.user
        request.auth = self.token
        view = type("View", (), {"token_resource": "cases"})()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_token_with_read_permission_post_request(self):
        """Test token with only read permission on POST request"""
        request = self.factory.post("/api/cases/")
        request.user = self.user
        request.auth = self.token
        view = type("View", (), {"token_resource": "cases"})()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_token_with_read_permission_delete_request(self):
        """Test token with only read permission on DELETE request"""
        request = self.factory.delete("/api/cases/1/")
        request.user = self.user
        request.auth = self.token
        view = type("View", (), {"token_resource": "cases"})()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_no_resource_specified(self):
        """Test that request is denied when no resource is specified"""
        request = self.factory.get("/api/cases/")
        request.user = self.user
        request.auth = self.token
        view = type("View", (), {})()  # No token_resource

        self.assertFalse(self.permission.has_permission(request, view))

    def test_get_action_mapping(self):
        """Test HTTP method to action mapping"""
        permission = HasTokenPermission()

        self.assertEqual(permission._get_action("GET"), "read")
        self.assertEqual(permission._get_action("HEAD"), "read")
        self.assertEqual(permission._get_action("OPTIONS"), "read")
        self.assertEqual(permission._get_action("POST"), "write")
        self.assertEqual(permission._get_action("PUT"), "write")
        self.assertEqual(permission._get_action("PATCH"), "write")
        self.assertEqual(permission._get_action("DELETE"), "delete")
