from jobqueue.models import *
from rest_framework import serializers
from networks.models import *


class JobAPISerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=JobModule.objects.all())
    # status defaults to 1 (PENDING) on the model.
    status = serializers.PrimaryKeyRelatedField(queryset=JobStatus.objects.all(), required=False)
    jobserver = serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all(), required=False, allow_null=True)
    class Meta:
        model = Job
        fields = '__all__'

class JobModuleAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = JobModule
        fields = '__all__'

class JobServerAPISerializer(serializers.ModelSerializer):
    jobmodules = serializers.PrimaryKeyRelatedField(many=True, queryset=JobModule.objects.all())
    network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False, allow_null=True)
    class Meta:
        model = JobServer
        fields = '__all__'