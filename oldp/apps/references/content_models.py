class ReferenceContent(object):
    """Content models that can contain references inherit from this.

    Subclasses implement :meth:`get_reference_marker_model` to return
    the concrete marker model (``CaseReferenceMarker`` for Case,
    ``LawReferenceMarker`` for Law). The reverse-relation accessor name
    on ``Reference`` is derived from the marker model's class name —
    ``CaseReferenceMarker`` → ``casereferencemarker``,
    ``LawReferenceMarker`` → ``lawreferencemarker`` — matching Django's
    default reverse lookup.
    """

    references = None
    reference_markers = None
    _reference_marker_pk_map = None

    def get_reference_marker_model(self):
        raise NotImplementedError()

    def _reverse_marker_accessor(self) -> str:
        """Reverse accessor on ``Reference`` for this content's marker model."""
        return self.get_reference_marker_model().__name__.lower()

    def get_references(self):
        """Reference rows attached to this content, via its marker model.

        Filters on ``<markermodel>__referenced_by=self`` so the query
        works for both Case and Law content. Without this indirection
        the query is hardcoded to one model and silently returns empty
        for the other.
        """
        if self.references is None:
            from oldp.apps.references.models import Reference

            self.references = Reference.objects.filter(
                **{f"{self._reverse_marker_accessor()}__referenced_by": self}
            ).select_related("law", "case")

        return self.references

    def get_reference_markers(self):
        if self.reference_markers is None:
            self.reference_markers = (
                self.get_reference_marker_model()
                .objects.filter(referenced_by=self)
                .prefetch_related("references")
            )
        return self.reference_markers

    def get_reference_marker_pk_map(self) -> dict:
        """Map ``Reference.pk`` -> owning marker pk, resolved in one query.

        ``Reference.get_marker()`` walks two reverse m2m accessors and costs up
        to two queries *per reference*. Templates that render one element per
        reference therefore issued O(2N) queries; on a law whose citation
        ranges had expanded into tens of thousands of rows that dominated the
        page, which is how a table-of-contents page came to take 88 seconds.

        Reading the through table directly collapses that to a single query.
        """
        if self._reference_marker_pk_map is None:
            through = self.get_reference_marker_model().references.through
            self._reference_marker_pk_map = dict(
                through.objects.filter(marker__referenced_by=self).values_list(
                    "reference_id", "marker_id"
                )
            )
        return self._reference_marker_pk_map

    def get_grouped_references(self) -> dict:
        """Group references by ``to_hash``."""
        grouped_refs = {}
        for ref in self.get_references():
            if ref.to_hash in grouped_refs:
                grouped_refs[ref.to_hash].append(ref)
            else:
                grouped_refs[ref.to_hash] = [ref]

        return grouped_refs
