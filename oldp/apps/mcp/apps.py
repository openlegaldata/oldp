from django.apps import AppConfig


class MCPConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "oldp.apps.mcp"
    verbose_name = "MCP Server"

    def ready(self):
        """Add titles and read-only hints to the registered MCP tools.

        ``mcp_server`` comes before this app in ``INSTALLED_APPS``, so its
        ``ready()`` has already discovered and registered every toolset.
        """
        from oldp.apps.mcp.annotations import apply_tool_annotations

        apply_tool_annotations()
