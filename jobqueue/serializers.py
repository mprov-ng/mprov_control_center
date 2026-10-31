from jobqueue.models import Job, JobModule, JobServer, JobStatus
from rest_framework import serializers
from networks.models import Network


class JobAPISerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=JobModule.objects.all())
    # status defaults to 1 (PENDING) on the model.
    status = serializers.PrimaryKeyRelatedField(queryset=JobStatus.objects.all(), required=False)
    jobserver = serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all(), required=False, allow_null=True)
    class Meta:
        model = Job
        fields = '__all__'

class JobDetailSerializer(serializers.ModelSerializer):
    """ GET /jobs/?detail: relations nested 3 levels deep (#298).  Not used
    for /jobs/<pk>/, which job servers read with status as an ID. """
    class Meta:
        model = Job
        fields = '__all__'
        depth = 3

class JobModuleAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = JobModule
        fields = '__all__'

class JobServerAPISerializer(serializers.ModelSerializer):
    jobmodules = serializers.PrimaryKeyRelatedField(many=True, queryset=JobModule.objects.all())
    network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False, allow_null=True)
    # heartbeated in the last minute (#254).
    responsive = serializers.BooleanField(read_only=True)
    class Meta:
        model = JobServer
        fields = '__all__'
        # only registration (POST /jobservers/) sets it (mprov_jobserver#113).
        read_only_fields = ('host_id',)
