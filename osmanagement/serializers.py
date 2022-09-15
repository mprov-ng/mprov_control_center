from osmanagement.models import *
from scripts.models import *
from jobqueue.models import *

from rest_framework import serializers

class OSDistroAPISerializer(serializers.ModelSerializer):
    baserepo = serializers.PrimaryKeyRelatedField(queryset=OSRepo.objects.all())
    osrepos = serializers.PrimaryKeyRelatedField(queryset=OSRepo.objects.all(), many=True)
    scripts = serializers.PrimaryKeyRelatedField(queryset=Script.objects.all(), many=True)

    class Meta:
        model = OSDistro
        fields = '__all__'

class OSRepoAPISerializer(serializers.ModelSerializer):
    hosted_by=serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all(), many=True)
    ostype=serializers.PrimaryKeyRelatedField(queryset=OSType.objects.all())
    class Meta:
        model = OSRepo
        fields = '__all__'
class OSTypeAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = OSType
        fields = '__all__'        