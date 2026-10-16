from rest_framework import serializers


class NestedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    '''
    A related field that is written as primary keys but read as nested
    objects, rendered by the given serializer class.  A writable nested
    serializer would need a custom create() and update(); this keeps the
    nested output while POST and PATCH take IDs.
    '''

    def __init__(self, serializer_class, **kwargs):
        self.serializer_class = serializer_class
        super().__init__(**kwargs)

    def use_pk_only_optimization(self):
        # to_representation needs the whole object, not just its pk.
        return False

    def to_representation(self, value):
        return self.serializer_class(value, context=self.context).data
