from jobqueue.models import *
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from networks.models import *


class JobAPISerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=JobModule.objects.all())
    status = serializers.PrimaryKeyRelatedField(queryset=JobStatus.objects.all())
    jobserver = serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all())
    class Meta:
        model = Job
        fields = '__all__'

class JobModuleAPISerializer(serializers.ModelSerializer):
    # slug is the primary key and editable=False on the model, which DRF
    # would make read-only, so POST couldn't set the module ID.  Declare it,
    # and refuse to change it on update: a new primary key would be a new row.
    slug = serializers.SlugField(max_length=255, validators=[UniqueValidator(queryset=JobModule.objects.all())])

    def validate_slug(self, value):
        if self.instance is not None and value != self.instance.slug:
            raise serializers.ValidationError("The module ID can't be changed.")
        return value

    class Meta:
        model = JobModule
        fields = '__all__'

class JobServerAPISerializer(serializers.ModelSerializer):
    jobmodules = serializers.PrimaryKeyRelatedField(queryset=JobModule.objects.all())
    network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all())
    class Meta:
        model = JobServer
        fields = '__all__'