from osmanagement.models import OSDistro, OSRepo
from rest_framework import serializers

class OSDistroAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSDistro
        fields = '__all__'

class OSRepoAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSRepo
        fields = '__all__'