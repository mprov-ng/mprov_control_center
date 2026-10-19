
from rest_framework import serializers

from common.serializers import NestedPrimaryKeyRelatedField
from .models import *

class ScriptTypeAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = ScriptType
        fields = '__all__'


class ScriptAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = Script
        fields = '__all__'
        # Script.save() makes the slug from the file name if it's not given.
        extra_kwargs = {'slug': {'required': False}}

    def validate(self, attrs):
        filename = attrs.get('filename', getattr(self.instance, 'filename', None))
        content = attrs.get('content', getattr(self.instance, 'content', None))
        if not filename and not content:
            raise serializers.ValidationError("Upload a script file or give its content.")
        return attrs

class AnsiblePlaybookAPISerializer(serializers.ModelSerializer):
    scriptType = ScriptTypeAPISerializer()
    class Meta:
        model = AnsiblePlaybook
        fields = '__all__'

class AnsibleRoleAPISerializer(serializers.ModelSerializer):
    scriptType = ScriptTypeAPISerializer()
    class Meta:
        model = AnsibleRole
        fields = '__all__'

class AnsibleCollectionAPISerializer(serializers.ModelSerializer):
    scriptType = ScriptTypeAPISerializer()
    class Meta:
        model = AnsibleCollection
        fields = '__all__'