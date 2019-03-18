from django.db.models import QuerySet, Q


class AnnotationContent(object):
    def get_annotation_model(self):
        raise NotImplementedError()

    def get_annotations(self, request=None) -> QuerySet:
        """
        Annotation query set depending on ownership and private attribute
        """

        qs = self.get_annotation_model().objects.filter(belongs_to=self).select_related('label')

        if request:
            if request.user.is_authenticated:
                if not request.user.is_staff:
                    qs = qs.filter(Q(label__private=False) | Q(label__owner=request.user))
            else:
                qs = qs.filter(label__private=False)

        return qs

    # def get_trusted_annotation(self, slug):
    #     try:
    #         # TODO many values
    #         annotation = self.get_annotation_model().objects.get(belongs_to=self, label__trusted=True, label__slug=slug)
    #         return annotation.value()
    #     except self.get_annotation_model().DoesNotExist:
    #         return None

    def get_annotation_labels(self, request=None) -> dict:
        """
        Build a dict with label_slug => annotation values
        """
        labels = dict()
        for obj in self.get_annotations(request):
            if obj.label.get_full_slug() not in labels:
                labels[obj.label.get_full_slug()] = obj.label

            labels[obj.label.get_full_slug()].annotations.append(obj.value())

        return labels

    def get_marker_model(self):
        raise NotImplementedError()

    def get_markers(self, request=None) -> QuerySet:
        """
        Annotation query set depending on ownership and private attribute
        """

        qs = self.get_marker_model().objects.filter(belongs_to=self).select_related('label')

        if request:
            if request.user.is_authenticated:
                if not request.user.is_staff:
                    qs = qs.filter(Q(label__private=False) | Q(label__owner=request.user))
            else:
                qs = qs.filter(label__private=False)

        return qs
