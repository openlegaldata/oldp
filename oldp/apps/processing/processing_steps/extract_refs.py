from refex.extractor import RefExtractor
from refex.models import RefType

from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import Reference


class BaseExtractRefs():
    extractor = RefExtractor()
    marker_model = None  # type: class[ReferenceMarker]

    def save_markers(self, markers, referenced_by):
        """Convert module objects into Django objects"""
        for marker in markers:  # type: RefMarker
            my_marker = self.marker_model(referenced_by=referenced_by, text=marker.text)
            my_marker.save()

            for ref in marker.references:
                my_ref = Reference(to=marker.text)
                my_ref.set_to_hash()

                # TODO assign based on marker text + context?
                if ref.ref_type == RefType.LAW:
                    # my_ref.law =
                    pass
                elif ref.ref_type == RefType.CASE:
                    pass
                else:
                    raise ProcessingError('Unsupported reference type: %s' % ref.ref_type)

                my_ref.save()
                my_marker.references.add(my_ref)
