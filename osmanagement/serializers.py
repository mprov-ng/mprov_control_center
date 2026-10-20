from osmanagement.models import OSDistro, OSRepo, OSType
from scripts.models import Script
from jobqueue.models import JobServer

from rest_framework import serializers

class OSDistroAPISerializer(serializers.ModelSerializer):
    baserepo = serializers.PrimaryKeyRelatedField(queryset=OSRepo.objects.all(), required=False, allow_null=True)
    osrepos = serializers.PrimaryKeyRelatedField(queryset=OSRepo.objects.all(), many=True, required=False)
    scripts = serializers.PrimaryKeyRelatedField(queryset=Script.objects.all(), many=True, required=False)

    class Meta:
        model = OSDistro
        fields = '__all__'

class OSRepoAPISerializer(serializers.ModelSerializer):
    hosted_by=serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all(), many=True, required=False)
    ostype=serializers.PrimaryKeyRelatedField(queryset=OSType.objects.all(), required=False, allow_null=True)
    class Meta:
        model = OSRepo
        fields = '__all__'
class OSTypeAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSType
        fields = '__all__'        