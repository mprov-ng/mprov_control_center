
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

class AnsiblePlaybookAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = AnsiblePlaybook
        fields = '__all__'
        # save() makes the slug if it's not given.
        extra_kwargs = {'slug': {'required': False}}

class AnsibleRoleAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = AnsibleRole
        fields = '__all__'
        # save() makes the slug if it's not given.
        extra_kwargs = {'slug': {'required': False}}

class AnsibleCollectionAPISerializer(serializers.ModelSerializer):
    # read as a nested object, written as an ID.
    scriptType = NestedPrimaryKeyRelatedField(ScriptTypeAPISerializer, queryset=ScriptType.objects.all())
    class Meta:
        model = AnsibleCollection
        fields = '__all__'
        # save() makes the slug if it's not given.
        extra_kwargs = {'slug': {'required': False}}

class FileAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = '__all__'
        # File.save() makes the slug from the file name if it's not given.
        extra_kwargs = {'slug': {'required': False}}
