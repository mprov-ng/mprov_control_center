

from rest_framework import serializers
from .models import Network, Switch, NetworkType, SwitchPort

class NetworkAPISerializer(serializers.ModelSerializer):
  net_type = serializers.PrimaryKeyRelatedField(queryset=NetworkType.objects.all())
  class Meta:
    model = Network
    fields = '__all__'

class NetworkDetailSerializer(serializers.ModelSerializer):
  """ GET /networks/<pk>/ and ?detail: relations nested 3 levels deep (#298).
  A depth-3 copy of NetworkAPISerializer would leave its declared net_type
  an ID. """
  class Meta:
    model = Network
    fields = '__all__'
    depth = 3

class NetworkTypeAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = NetworkType
    fields = '__all__'

class SwitchAPISerializer(serializers.ModelSerializer):
  # set from the request user by the UpdateSwitch pre_save signal.
  created_by = serializers.PrimaryKeyRelatedField(read_only=True)
  network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False, allow_null=True)
  class Meta:
    model = Switch
    fields = '__all__'

class SwitchPortAPISerializer(serializers.ModelSerializer):
  switch = serializers.PrimaryKeyRelatedField(queryset=Switch.objects.all())
  networks = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False, allow_null=True)

  class Meta:
    model = SwitchPort
    fields = '__all__'
