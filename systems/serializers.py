from array import array
from pyexpat import model
from systems.models import NetworkInterface, SystemImage, System, SystemGroup, SystemBMC, SystemModel
from rest_framework import serializers
from jobqueue.models import JobServer
from disklayouts.serializers import DiskLayoutAPISerializer
from networks.models import SwitchPort, Network
from scripts.models import Script
from scripts.serializers import ScriptAPISerializer, AnsibleCollectionAPISerializer, AnsiblePlaybookAPISerializer, AnsibleRoleAPISerializer

class SystemSerializer(serializers.ModelSerializer): 
    config = serializers.DictField(allow_empty=True, required=False)
    class Meta:
        model = System
        fields = '__all__'
class SystemBMCSerializer(serializers.ModelSerializer): 
    system = serializers.PrimaryKeyRelatedField(queryset=System.objects.all())
    switch_port = serializers.PrimaryKeyRelatedField(queryset=SwitchPort.objects.all(),required=False)
    network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False)
    class Meta:
        model = SystemBMC
        fields = '__all__'
        # Accept the password on POST/PATCH but never return it. Only the ?detail
        # serializer returns it, because mprov_scripts' setupBMC.py needs it.
        extra_kwargs = {'password': {'write_only': True}}
class SystemGroupSerializer(serializers.ModelSerializer): 
    scripts = ScriptAPISerializer(many=True)
    ansibleplaybooks = AnsiblePlaybookAPISerializer(many=True)
    ansibleroles = AnsibleRoleAPISerializer(many=True)
    ansiblecollections = AnsibleCollectionAPISerializer(many=True)
    class Meta:
        model = SystemGroup
        fields = '__all__' 
class SystemImageSerializer(serializers.ModelSerializer):
    jobservers=serializers.PrimaryKeyRelatedField(many=True, queryset=JobServer.objects.all())
    systemgroups=SystemGroupSerializer(many=True)
    class Meta:
        model = SystemImage
        fields = '__all__'
class SystemImageDetailsSerializer(SystemImageSerializer):
    class Meta:
        model = SystemImage
        depth = 3
        fields = '__all__'
class SystemDetailSerializer(serializers.ModelSerializer): 
    disks = DiskLayoutAPISerializer(many=True, read_only=True)
    systemimage = SystemImageDetailsSerializer(many=False)
    systemmodel =  serializers.PrimaryKeyRelatedField(queryset=SystemModel.objects.all())
    config = serializers.DictField()
    systemgroups = SystemGroupSerializer(many=True)
    ansibleplaybooks = AnsiblePlaybookAPISerializer(many=True)
    ansibleroles = AnsibleRoleAPISerializer(many=True)
    ansiblecollections = AnsibleCollectionAPISerializer(many=True)
    class Meta:
        model = System
        fields = '__all__'
        depth = 3
class SystemBMCDetailSerializer(serializers.ModelSerializer): 
    
    class Meta:
        model = SystemBMC
        fields = '__all__'# ['id','switch_port','system', 'system_detail', 'network', 'ipaddress', 'mac', 'username', 'password']
        depth = 1        

        
class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'

class NetworkInterfaceDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'
        depth=3
