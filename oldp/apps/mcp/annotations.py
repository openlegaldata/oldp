"""Human-readable titles and behaviour hints for the OLDP MCP tools.

MCP clients show the tool ``title`` instead of its machine name, and use
the ``ToolAnnotations`` hints (``readOnlyHint``, ``destructiveHint``, ...)
to decide whether a call needs user confirmation. Directories such as the
Claude connector directory require both on every tool.

django-mcp-server registers toolset methods without either, so
:func:`apply_tool_annotations` sets them on the registered tools once all
toolsets are loaded (see :meth:`oldp.apps.mcp.apps.MCPConfig.ready`).

Almost every OLDP tool only reads from the platform's own database and
search index, so tools get :data:`READ_ONLY_HINTS` unless
:data:`TOOL_HINTS` overrides them (e.g. ``submit_feedback``, which sends
an email). When adding a tool, add its title to :data:`TOOL_TITLES` (and
to :data:`TOOL_HINTS` if it is not read-only); the test suite fails for
any registered tool without a title.
"""

import logging

from mcp.types import ToolAnnotations

logger = logging.getLogger(__name__)

#: Hints shared by all OLDP tools: they never modify data, repeated calls
#: with the same arguments have no additional effect, and they only touch
#: OLDP's own (closed) data set rather than the open web.
READ_ONLY_HINTS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

#: Tool name -> human-readable title shown by MCP clients.
TOOL_TITLES = {
    # Platform / discovery (oldp.apps.mcp.mcp)
    "get_platform_info": "Get platform coverage",
    "whoami": "Show connection and rate limit",
    "search_legal": "Search laws and court decisions",
    # Built-in tool registered by django-mcp-server
    "get_server_instructions": "Get server instructions",
    # Courts (oldp.apps.courts.mcp)
    "list_courts": "List courts",
    "get_court": "Get court details",
    # Laws (oldp.apps.laws.mcp)
    "list_law_books": "List law books",
    "get_law_section": "Get law section",
    "search_laws": "Search laws",
    # Cases (oldp.apps.cases.mcp)
    "search_cases": "Search court decisions",
    "get_similar_cases": "Find similar court decisions",
    "filter_cases": "Filter court decisions",
    "get_case": "Get court decision",
    "get_case_statistics": "Get court decision statistics",
    # References (oldp.apps.references.mcp)
    "validate_citation": "Validate legal citation",
    "get_case_references": "Get references in a decision",
    "get_citing_cases": "Find decisions citing a decision",
    "get_cases_for_law": "Find decisions citing a law",
    # Feedback (oldp.apps.contact.mcp)
    "submit_feedback": "Send feedback to OLDP",
}

#: Tool name -> hints for tools that are not read-only.
TOOL_HINTS = {
    # Sends an email to the OLDP team; repeated calls send repeated emails.
    "submit_feedback": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
}


def apply_tool_annotations(server=None) -> list[str]:
    """Set ``title`` and ``annotations`` on all registered tools.

    Args:
        server: The ``DjangoMCP`` server whose tools to annotate. Defaults
            to django-mcp-server's global server, which serves ``/mcp``.

    Returns:
        Names of registered tools that have no entry in
        :data:`TOOL_TITLES`. They still get hints but no title; a
        warning is logged for each.
    """
    if server is None:
        from mcp_server.djangomcp import global_mcp_server

        server = global_mcp_server

    untitled = []
    for tool in server._tool_manager.list_tools():
        title = TOOL_TITLES.get(tool.name)
        if title is None:
            untitled.append(tool.name)
            logger.warning("MCP tool %r has no title in TOOL_TITLES", tool.name)
        tool.title = title
        hints = TOOL_HINTS.get(tool.name, READ_ONLY_HINTS)
        tool.annotations = ToolAnnotations(title=title, **hints)
    return untitled
