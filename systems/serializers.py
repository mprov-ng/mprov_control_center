from systems.models import SystemImage
from rest_framework import serializers
from jobqueue.serializers import JobServerAPISerializer
from jobqueue.models import JobServer

class SystemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'
        depth = 3
        
class SystemImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'
        
    # def update(self, instance, validated_data):
    #     jobservers_data = validated_data.pop('jobservers')
    #     print("JS Data: " + jobservers_data)
    #     image = super().update(instance, validated_data)
    #     image.save()

    #     for jobserver in jobservers_data:
    #         js = JobServer.objects.get(pk=jobserver)
    #         print("Jobserver: " + str(js))
    #         image.jobservers.add(js)
        
    #     return image