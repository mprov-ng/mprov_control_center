from systems.models import NetworkInterface, SystemImage, System, SystemGroup, SystemBMC, SystemModel
from rest_framework import serializers
from jobqueue.models import JobServer
from disklayouts.serializers import DiskLayoutAPISerializer
from networks.models import SwitchPort, Network
from scripts.models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection
from common.serializers import NestedPrimaryKeyRelatedField, NoNestedUsersMixin
from common.permissions import node_system
from networks.serializers import GuidField
from scripts.serializers import ScriptAPISerializer, AnsibleCollectionAPISerializer, AnsiblePlaybookAPISerializer, AnsibleRoleAPISerializer

class SystemSerializer(serializers.ModelSerializer): 
    """ A system, with relations as IDs, plus its merged config (read-only). """
    config = serializers.DictField(read_only=True)
    class Meta:
        model = System
        fields = '__all__'
        read_only_fields = ['created_by', 'updated_by']

    def save(self, **kwargs):
        # keep a serial number set through the API in the system's serial
        # history (#60).
        old = self.instance.serial if self.instance is not None else None
        system = super().save(**kwargs)
        request = self.context.get('request')
        system.record_serial_change(old, system.serial, "api", getattr(request, 'user', None))
        return system
class SystemBMCSerializer(serializers.ModelSerializer): 
    """ A BMC; the password is accepted but never returned here. """
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
    """ A system group; scripts and Ansible are nested objects when read and IDs when
    written. """
    scripts = NestedPrimaryKeyRelatedField(ScriptAPISerializer, many=True, required=False, queryset=Script.objects.all())
    ansibleplaybooks = NestedPrimaryKeyRelatedField(AnsiblePlaybookAPISerializer, many=True, required=False, queryset=AnsiblePlaybook.objects.all())
    ansibleroles = NestedPrimaryKeyRelatedField(AnsibleRoleAPISerializer, many=True, required=False, queryset=AnsibleRole.objects.all())
    ansiblecollections = NestedPrimaryKeyRelatedField(AnsibleCollectionAPISerializer, many=True, required=False, queryset=AnsibleCollection.objects.all())
    class Meta:
        model = SystemGroup
        fields = '__all__' 
class SystemImageSerializer(serializers.ModelSerializer):
    """ A system image. """
    jobservers=serializers.PrimaryKeyRelatedField(many=True, queryset=JobServer.objects.all())
    # read as nested objects, written as IDs.
    systemgroups=NestedPrimaryKeyRelatedField(SystemGroupSerializer, many=True, required=False, queryset=SystemGroup.objects.all())
    config = serializers.DictField(read_only=True)
    class Meta:
        model = SystemImage
        fields = '__all__'
        read_only_fields = ['created_by', 'updated_by']
class SystemImageDetailsSerializer(NoNestedUsersMixin, SystemImageSerializer):
    """ A system image with its relations nested three deep, for ?detail. """
    class Meta:
        model = SystemImage
        depth = 3
        fields = '__all__'
        read_only_fields = ['created_by', 'updated_by']
class SystemDetailSerializer(NoNestedUsersMixin, serializers.ModelSerializer): 
    """ A system with its image, groups, disks and Ansible nested, plus its merged
    config, for ?detail and ?self. """
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
        read_only_fields = ['created_by', 'updated_by']
class SystemBMCDetailSerializer(NoNestedUsersMixin, serializers.ModelSerializer): 
    
    """ A BMC with its system nested, including the password, for the per-system paths
    setupBMC.py reads. """
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
    """ A NIC; hostname is read-only, copied from its system on every save (#382). """
    guid = GuidField(NetworkInterface)

    class Meta:
        model = NetworkInterface
        fields = '__all__'
        # copied from the System on every save (NetworkInterface.save()), so
        # a value sent here would be overwritten anyway (#382).
        read_only_fields = ['hostname']

    def validate(self, attrs):
        """ A node writing its own NICs (#566) may not take a MAC another system
        has, or a switch port on a network other than the NIC's.  A 400 that
        says which, so a node can tell it from a 403 rule refusal. """
        attrs = super().validate(attrs)
        request = self.context.get('request')
        node = node_system(request) if request is not None else None
        if node is None:
            return attrs
        errors = {}
        mac = attrs.get('mac')
        if mac:
            taken = (NetworkInterface.objects.filter(mac__iexact=mac).exclude(system=node).exists()
                     or SystemBMC.objects.filter(mac__iexact=mac).exclude(system=node).exists())
            if taken:
                errors['mac'] = "Another system already has this MAC address."
        port = attrs.get('switch_port')
        if port is not None:
            network = attrs['network'] if 'network' in attrs else getattr(self.instance, 'network', None)
            if port.networks_id is not None and port.networks_id != getattr(network, 'pk', None):
                errors['switch_port'] = "This switch port is on a different network from this interface."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

class NetworkInterfaceDetailsSerializer(NoNestedUsersMixin, serializers.ModelSerializer):
    """ A NIC with its system, network and switch port nested three deep; hostname is
    read-only. """
    class Meta:
        model = NetworkInterface
        fields = '__all__'
        read_only_fields = ['hostname']
        depth=3
