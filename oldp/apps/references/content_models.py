class ReferenceContent(object):
    """
    Content models that can contain references inherit from this
    """
    references = None
    reference_markers = None

    def get_reference_marker_model(self):
        raise NotImplementedError()

    def get_references(self):
        """
        Get reference with custom query (grouped by to_hash).
        :return:
        """
        if self.references is None:
            from oldp.apps.references.models import Reference
            self.references = Reference.objects.filter(casereferencemarker__referenced_by=self)

        return self.references

    def get_reference_markers(self):
        if self.reference_markers is None:
            self.reference_markers = self.get_reference_marker_model().objects.filter(referenced_by=self)
        return self.reference_markers

    def get_grouped_references(self) -> dict:
        """
        Group references by `to_hash` field.
        """


        grouped_refs = {}
        for ref in self.get_references():
            if ref.to_hash in grouped_refs:
                grouped_refs[ref.to_hash].append(ref)
            else:
                grouped_refs[ref.to_hash] = [ref]

        return grouped_refs
