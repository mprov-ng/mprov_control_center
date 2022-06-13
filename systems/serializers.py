from pyexpat import model
from systems.models import NetworkInterface, SystemImage, System, SystemGroup
from rest_framework import serializers
from jobqueue.models import JobServer

class SystemSerializer(serializers.ModelSerializer): 
    class Meta:
        model = System
        fields = '__all__'
class SystemGroupSerializer(serializers.ModelSerializer): 
    class Meta:
        model = SystemGroup
        fields = '__all__'
class SystemDetailSerializer(serializers.ModelSerializer): 
    class Meta:
        model = System
        fields = '__all__'
        depth = 3
class SystemImageDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'
        depth = 3
        
class SystemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'


    def update(self, instance, validated_data):
        print(f"{validated_data}")
        jobservers_data = validated_data.pop('jobservers')
        print("JS Data: " + str(jobservers_data))
        image = super().update(instance, validated_data)
        image.save()

        for jobserver in jobservers_data:
            image.jobservers.add(jobserver.pk)
        
        return image
class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'

class NetworkInterfaceDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'
        depth=3
