from systems.models import SystemImage
from rest_framework import serializers

class SystemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'
        depth = 3
