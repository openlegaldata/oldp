"""Reference / citation services.

Pure-Python query helpers for the citation graph and citation
validation. The MCP toolset and the REST API both delegate here so
query and serialization logic stays single-sourced.
"""

from oldp.apps.references.services.citation_graph import (
    CITATION_NOTE,
    case_forward_references,
    citing_cases_for_case,
    citing_cases_for_law,
    citing_laws_for_case,
    citing_laws_for_law,
    law_forward_references,
    resolve_law_section,
    serialize_case_summary,
    serialize_law_summary,
)
from oldp.apps.references.services.citation_lookup import (
    parse_citation_type,
    section_variants,
    validate_citation,
)

__all__ = [
    "CITATION_NOTE",
    "case_forward_references",
    "citing_cases_for_case",
    "citing_cases_for_law",
    "citing_laws_for_case",
    "citing_laws_for_law",
    "law_forward_references",
    "parse_citation_type",
    "resolve_law_section",
    "section_variants",
    "serialize_case_summary",
    "serialize_law_summary",
    "validate_citation",
]
