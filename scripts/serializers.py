
from rest_framework import serializers

from .models import *

class ScriptTypeAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = ScriptType
        fields = '__all__'


class ScriptAPISerializer(serializers.ModelSerializer):
    scriptType = ScriptTypeAPISerializer()
    class Meta:
        model = Script
        fields = '__all__'