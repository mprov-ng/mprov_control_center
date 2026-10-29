from systems.models import NetworkInterface, SystemImage, System, SystemGroup, SystemBMC, SystemModel
from rest_framework import serializers
from jobqueue.models import JobServer
from disklayouts.serializers import DiskLayoutAPISerializer
from networks.models import SwitchPort, Network
from scripts.models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection
from common.serializers import NestedPrimaryKeyRelatedField
from scripts.serializers import ScriptAPISerializer, AnsibleCollectionAPISerializer, AnsiblePlaybookAPISerializer, AnsibleRoleAPISerializer

class SystemSerializer(serializers.ModelSerializer): 
    config = serializers.DictField(read_only=True)
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
        # Accept the password on POST/PATCH but never return it. Only the
        # per-system detail paths return it (see SystemBMCAPIView), because
        # mprov_scripts' setupBMC.py needs it.
        extra_kwargs = {'password': {'write_only': True}}
class SystemGroupSerializer(serializers.ModelSerializer): 
    # read as nested objects, written as IDs.
    scripts = NestedPrimaryKeyRelatedField(ScriptAPISerializer, many=True, required=False, queryset=Script.objects.all())
    ansibleplaybooks = NestedPrimaryKeyRelatedField(AnsiblePlaybookAPISerializer, many=True, required=False, queryset=AnsiblePlaybook.objects.all())
    ansibleroles = NestedPrimaryKeyRelatedField(AnsibleRoleAPISerializer, many=True, required=False, queryset=AnsibleRole.objects.all())
    ansiblecollections = NestedPrimaryKeyRelatedField(AnsibleCollectionAPISerializer, many=True, required=False, queryset=AnsibleCollection.objects.all())
    class Meta:
        model = SystemGroup
        fields = '__all__' 
class SystemImageSerializer(serializers.ModelSerializer):
    jobservers=serializers.PrimaryKeyRelatedField(many=True, queryset=JobServer.objects.all())
    # read as nested objects, written as IDs.
    systemgroups=NestedPrimaryKeyRelatedField(SystemGroupSerializer, many=True, required=False, queryset=SystemGroup.objects.all())
    config = serializers.DictField(read_only=True)
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
    config = serializers.DictField(read_only=True)
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
class SystemBMCDetailNoPasswordSerializer(SystemBMCDetailSerializer):
    """ Same nesting as SystemBMCDetailSerializer, without the password, for
    ?detail queries that are not scoped to one system: one unscoped GET must
    not return every BMC password (issue #316). The per-system paths keep
    using SystemBMCDetailSerializer. """
    class Meta(SystemBMCDetailSerializer.Meta):
        extra_kwargs = {'password': {'write_only': True}}

        
class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'
        # copied from the System on every save (NetworkInterface.save()), so
        # a value sent here would be overwritten anyway (#382).
        read_only_fields = ['hostname']

class NetworkInterfaceDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'
        read_only_fields = ['hostname']
        depth=3
