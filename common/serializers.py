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


class NoNestedUsersMixin:
    '''
    For a ModelSerializer with depth: render a relation to the user model as
    its primary key, as responses without depth already do, never as a nested
    user record.  Every other nested relation is built with this mixin too,
    so the rule holds at every depth.
    '''

    def build_nested_field(self, field_name, relation_info, nested_depth):
        from django.contrib.auth import get_user_model
        from rest_framework.utils.field_mapping import get_nested_relation_kwargs
        if relation_info.related_model is get_user_model():
            kwargs = {'read_only': True}
            if relation_info.to_many:
                kwargs['many'] = True
            return serializers.PrimaryKeyRelatedField, kwargs

        class NestedSerializer(NoNestedUsersMixin, serializers.ModelSerializer):
            class Meta:
                model = relation_info.related_model
                depth = nested_depth - 1
                fields = '__all__'

        return NestedSerializer, get_nested_relation_kwargs(relation_info)
