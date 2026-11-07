
from rest_framework import serializers

from common.serializers import NestedPrimaryKeyRelatedField
from .models import AnsibleCollection, AnsiblePlaybook, AnsibleRole, File, Script, ScriptType

def require_script_type(serializer, attrs):
    # a partial update of a script whose type was deleted before #310 would
    # otherwise fail in save() with a 500.  (A create already requires the
    # field.)
    if serializer.instance is not None and attrs.get('scriptType', serializer.instance.scriptType) is None:
        raise serializers.ValidationError({'scriptType': "Choose a type."})


class ScriptTypeAPISerializer(serializers.ModelSerializer):
    """ A script type, e.g. image-gen or post-boot. """
    class Meta:
        model = ScriptType
        fields = '__all__'


class ScriptAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    """ A script, with its type nested when read and an ID when written; needs a file or
    content, and a type. """
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
        require_script_type(self, attrs)
        return attrs

class AnsiblePlaybookAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    """ An Ansible playbook, with its type nested when read and an ID when written. """
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = AnsiblePlaybook
        fields = '__all__'
        # save() makes the slug if it's not given.
        extra_kwargs = {'slug': {'required': False}}

    def validate(self, attrs):
        require_script_type(self, attrs)
        return attrs

class AnsibleRoleAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    """ An Ansible role, with its type nested when read and an ID when written. """
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = AnsibleRole
        fields = '__all__'
        # save() makes the slug if it's not given.
        extra_kwargs = {'slug': {'required': False}}

class AnsibleCollectionAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    """ An Ansible collection, with its type nested when read and an ID when written. """
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = AnsibleCollection
        fields = '__all__'
        # save() makes the slug if it's not given.
        extra_kwargs = {'slug': {'required': False}}

class FileAPISerializer(serializers.ModelSerializer):
    """ An uploaded file. """
    class Meta:
        model = File
        fields = '__all__'
        # File.save() makes the slug from the file name if it's not given.
        extra_kwargs = {'slug': {'required': False}}
