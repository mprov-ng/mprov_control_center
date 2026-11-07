from osmanagement.models import OSDistro, OSRepo, OSType, base_image_problem
from scripts.models import Script
from jobqueue.models import JobServer

from rest_framework import serializers

class OSDistroAPISerializer(serializers.ModelSerializer):
    """ An OS distribution.  The root password is write-only, and a base image URL needs
    a checksum, checked on a partial update too (#429). """
    baserepo = serializers.PrimaryKeyRelatedField(queryset=OSRepo.objects.all(), required=False, allow_null=True)
    osrepos = serializers.PrimaryKeyRelatedField(queryset=OSRepo.objects.all(), many=True, required=False)
    scripts = serializers.PrimaryKeyRelatedField(queryset=Script.objects.all(), many=True, required=False)

    class Meta:
        model = OSDistro
        fields = '__all__'
        # Accept rootpw on POST/PATCH but never return it, as for the BMC
        # password. The jobserver reads it from the osdistro nested inside
        # /systemimages/<slug>/, where it is still present. (#313)
        extra_kwargs = {'rootpw': {'write_only': True}}

    def validate(self, attrs):
        # DRF doesn't call OSDistro.clean().  On a PATCH, a field that isn't
        # sent keeps its stored value. (#429)
        def value(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, "") if self.instance else ""
        problem = base_image_problem(value('base_image_url'), value('base_image_checksum'))
        if problem:
            raise serializers.ValidationError({'base_image_checksum': problem})
        return attrs

class OSRepoAPISerializer(serializers.ModelSerializer):
    """ An OS repository. """
    hosted_by=serializers.PrimaryKeyRelatedField(queryset=JobServer.objects.all(), many=True, required=False)
    ostype=serializers.PrimaryKeyRelatedField(queryset=OSType.objects.all(), required=False, allow_null=True)
    class Meta:
        model = OSRepo
        fields = '__all__'
class OSTypeAPISerializer(serializers.ModelSerializer):
    """ An OS type. """
    class Meta:
        model = OSType
        fields = '__all__'        