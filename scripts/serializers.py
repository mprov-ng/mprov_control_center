
from rest_framework import serializers

from .models import Script

class ScriptAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = Script
        fields = '__all__'