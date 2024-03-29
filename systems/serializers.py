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
class SystemGroupSerializer(serializers.ModelSerializer): 
    scripts = ScriptAPISerializer(many=True)
    ansibleplaybooks = AnsiblePlaybookAPISerializer(many=True)
    ansibleroles = AnsibleRoleAPISerializer(many=True)
    ansiblecollections = AnsibleCollectionAPISerializer(many=True)
    class Meta:
        model = SystemGroup
        fields = '__all__' 
class SystemGroupDetailSerializer(serializers.ModelSerializer): 
    scripts = ScriptAPISerializer(many=True)
    class Meta:
        model = SystemGroup
        fields = '__all__'
        depth = 2
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

        
class a(serializers.ModelSerializer):
    jobservers=serializers.PrimaryKeyRelatedField(many=True, queryset=JobServer.objects.all(),)
    class Meta:
        model = SystemImage
        fields = ['version', 'name', 'slug', 'jobservers', 'osdistro']#'__all__'
        

    def validate_jobservers(self, value):
        print(f"Prevalidation jobservers:'{value}'")
        return value
    
    def check_jobservers(self, validated_data):
        if 'jobservers' in self.initial_data and not 'jobservers' in validated_data:
            print(f"ODD BUG DETECTED!  FIXING JOBSERVERS!")
            validated_data['jobservers'] = []
            for jsid in self.initial_data['jobservers']:
                # look up the job server
                js = JobServer.objects.get(pk=jsid)
                validated_data['jobservers'].append(js)
        print(f"check_jobservers: {validated_data}")


    def update(self, instance, validated_data):
        print(f"Dumping data: {self.initial_data}")

        self.check_jobservers(validated_data)
        print(f"{validated_data}")
        image = super().update(instance, validated_data)
        image.save()
        if 'jobservers' in validated_data:
            jobservers_data = validated_data.pop('jobservers')
            print("JS Data: " + str(jobservers_data))
            

            for jobserver in jobservers_data:
                image.jobservers.add(jobserver.pk)
        else:
            print(f"No jobserver in update, not changing.")
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
