from pyexpat import model
from systems.models import NetworkInterface, SystemImage, System, SystemGroup
from rest_framework import serializers

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
class SystemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'
        depth = 3
        
class SystemImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemImage
        fields = '__all__'
class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'

class NetworkInterfaceDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'
        depth=3
