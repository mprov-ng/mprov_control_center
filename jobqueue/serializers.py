from jobqueue.models import *
from rest_framework import serializers
from networks.models import *


class JobAPISerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=JobModule.objects.all())
    status = serializers.PrimaryKeyRelatedField(queryset=JobStatus.objects.all())
    jobserver = serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all())
    class Meta:
        model = Job
        fields = '__all__'

class JobModuleAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = JobModule
        fields = '__all__'

class JobServerAPISerializer(serializers.ModelSerializer):
    jobmodules = serializers.PrimaryKeyRelatedField(queryset=JobModule.objects.all())
    network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all())
    class Meta:
        model = JobServer
        fields = '__all__'