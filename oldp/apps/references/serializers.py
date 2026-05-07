"""Serializers for the references REST API."""

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
