"""Serializers for the references REST API.

Most serializers project model rows into the response shape. The
``ForwardReferences*`` and ``CitationValidation*`` serializers are
**schema-only** stand-ins for the dict payloads produced by
``oldp.apps.references.services``. They aren't used to validate or
build responses (the service functions already return the final
shape); they exist so ``drf-yasg`` can render an accurate OpenAPI /
Swagger spec for the ``@swagger_auto_schema(responses=…)`` decorators
on the citation actions.
"""

from __future__ import annotations

from rest_framework import serializers

from oldp.apps.references.models import Reference


class ReferenceTargetCaseSerializer(serializers.Serializer):
    """Compact case projection used as a citation target."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)
    file_number = serializers.CharField(read_only=True)
    date = serializers.DateField(read_only=True)


class ReferenceTargetLawSerializer(serializers.Serializer):
    """Compact law projection used as a citation target."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)
    section = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    book_id = serializers.IntegerField(read_only=True)
    book_slug = serializers.SerializerMethodField()
    book_code = serializers.SerializerMethodField()

    def get_book_slug(self, law) -> str:
        return law.book.slug if law.book_id else ""

    def get_book_code(self, law) -> str:
        return law.book.code if law.book_id else ""


class ReferenceSerializer(serializers.ModelSerializer):
    """Full ``Reference`` row for the flat ``/api/references/`` resource.

    Surfaces the citation as a record of (source_kind, source_id) →
    (target_kind, target_id), via the through-table marker. Source is
    derived from the marker; target is the FK on the ``Reference``
    itself.
    """

    case = ReferenceTargetCaseSerializer(read_only=True, allow_null=True)
    law = ReferenceTargetLawSerializer(read_only=True, allow_null=True)
    cited_by = serializers.SerializerMethodField()
    marker_text = serializers.SerializerMethodField()

    class Meta:
        model = Reference
        fields = (
            "id",
            "to",
            "to_hash",
            "case",
            "law",
            "cited_by",
            "marker_text",
        )
        read_only_fields = fields

    def get_cited_by(self, ref) -> dict | None:
        """Identify the source content + the marker that emitted the cite.

        Reference rows are attached to either a case marker (via the
        ``ReferenceFromCase`` through-table) or a law marker (via
        ``ReferenceFromLaw``). For the flat API we surface a uniform
        ``{kind, id, slug, marker_text}`` shape regardless of source.
        """
        rfc = ref.referencefromcase_set.first()
        if rfc is not None:
            src = rfc.marker.referenced_by
            return {
                "kind": "case",
                "id": src.id,
                "slug": src.slug,
                "file_number": src.file_number,
            }
        rfl = ref.referencefromlaw_set.first()
        if rfl is not None:
            src = rfl.marker.referenced_by
            return {
                "kind": "law",
                "id": src.id,
                "slug": src.slug,
                "section": src.section,
                "book_slug": src.book.slug if src.book_id else "",
            }
        return None

    def get_marker_text(self, ref) -> str:
        """Marker.text on the source side, regardless of case/law origin."""
        rfc = ref.referencefromcase_set.first()
        if rfc is not None:
            return rfc.marker.text
        rfl = ref.referencefromlaw_set.first()
        if rfl is not None:
            return rfl.marker.text
        return ""


# --- Schema-only serializers (used solely by drf-yasg decorators) -------


class ForwardReferenceLawTargetSerializer(serializers.Serializer):
    """A law target inside a ``forward_references`` payload."""

    id = serializers.IntegerField(read_only=True)
    book_code = serializers.CharField(read_only=True)
    book_slug = serializers.CharField(read_only=True)
    section = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    marker_text = serializers.CharField(read_only=True)


class ForwardReferenceCaseTargetSerializer(serializers.Serializer):
    """A case target inside a ``forward_references`` payload."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)
    file_number = serializers.CharField(read_only=True)
    date = serializers.DateField(read_only=True)
    marker_text = serializers.CharField(read_only=True)


class ForwardReferencesResponseSerializer(serializers.Serializer):
    """Response shape for ``/cases/<id>/references/`` and ``/laws/<id>/references/``.

    Mirrors the dict produced by
    :func:`oldp.apps.references.services.case_forward_references` /
    :func:`~oldp.apps.references.services.law_forward_references`. The
    case- and law-rooted variants share every field except for the
    primary-key flavour: case payloads carry ``case_id`` +
    ``case_file_number``; law payloads carry ``law_id`` +
    ``law_section``. We document both pairs as optional here so a
    single serializer covers both endpoints.
    """

    case_id = serializers.IntegerField(read_only=True, required=False)
    case_file_number = serializers.CharField(read_only=True, required=False)
    law_id = serializers.IntegerField(read_only=True, required=False)
    law_section = serializers.CharField(read_only=True, required=False)
    total_law_references = serializers.IntegerField(read_only=True)
    total_case_references = serializers.IntegerField(read_only=True)
    law_references = ForwardReferenceLawTargetSerializer(many=True, read_only=True)
    case_references = ForwardReferenceCaseTargetSerializer(many=True, read_only=True)
    references_extracted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    note = serializers.CharField(read_only=True)


class CitationValidationMatchCaseSerializer(serializers.Serializer):
    """Single case match inside a ``validate_citation`` response."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)
    file_number = serializers.CharField(read_only=True)
    date = serializers.DateField(read_only=True, allow_null=True)
    court = serializers.CharField(read_only=True, allow_null=True)
    ecli = serializers.CharField(read_only=True, allow_null=True)


class CitationValidationMatchLawSerializer(serializers.Serializer):
    """Single law match inside a ``validate_citation`` response."""

    id = serializers.IntegerField(read_only=True)
    book_code = serializers.CharField(read_only=True)
    section = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)


class CitationValidationResponseSerializer(serializers.Serializer):
    """Response shape for ``/api/citations/validate/``.

    Either ``matches`` is populated (success) or ``message`` is set
    (not-found / parse-error). The serializer documents both cases as
    optional so the schema reflects either path. A request-level
    ``error`` field handles the empty-input case.
    """

    found = serializers.BooleanField(read_only=True, required=False)
    type = serializers.CharField(read_only=True, required=False)
    citation_type = serializers.CharField(read_only=True, required=False)
    matches = serializers.ListField(
        child=serializers.DictField(), read_only=True, required=False
    )
    message = serializers.CharField(read_only=True, required=False)
    error = serializers.CharField(read_only=True, required=False)
