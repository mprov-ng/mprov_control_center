
from rest_framework import serializers

from .models import *

class ScriptAPISerializer(serializers.ModelSerializer):
    scriptType = serializers.PrimaryKeyRelatedField(queryset=ScriptType.objects.all())
    class Meta:
        model = Script
        fields = '__all__'