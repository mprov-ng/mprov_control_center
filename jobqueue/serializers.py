from jobqueue.models import JobModule, JobServer, Job
from rest_framework import serializers


class JobAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'

class JobModuleAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = JobModule
        fields = '__all__'

class JobServerAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = JobServer
        fields = '__all__'