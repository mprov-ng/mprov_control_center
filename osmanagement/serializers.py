from osmanagement.models import OSDistro, OSRepo, OSType
from rest_framework import serializers

class OSDistroAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSDistro
        fields = '__all__'

class OSRepoAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSRepo
        fields = '__all__'
class OSTypeAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSType
        fields = '__all__'        