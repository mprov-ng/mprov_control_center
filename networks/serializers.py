

from rest_framework import serializers
from common.serializers import NoNestedUsersMixin
from rest_framework.validators import UniqueValidator
from .models import Network, Switch, NetworkType, SwitchPort, GUID_VALIDATOR, normalize_guid


class GuidField(serializers.CharField):
  """ An InfiniBand GUID (#566), lowercased before it's checked for uniqueness,
  so 0xABC... and 0xabc... are the same GUID.  Empty is stored as NULL. """
  def __init__(self, model, **kwargs):
    super().__init__(max_length=19, required=False, allow_null=True, allow_blank=True,
                     validators=[GUID_VALIDATOR, UniqueValidator(queryset=model.objects.all())], **kwargs)

  def to_internal_value(self, data):
    return normalize_guid(super().to_internal_value(data))

class NetworkAPISerializer(serializers.ModelSerializer):
  """ A network, with its network type as an ID. """
  net_type = serializers.PrimaryKeyRelatedField(queryset=NetworkType.objects.all())
  class Meta:
    model = Network
    fields = '__all__'

class NetworkDetailSerializer(NoNestedUsersMixin, serializers.ModelSerializer):
  """ GET /networks/<pk>/ and ?detail: relations nested 3 levels deep (#298).
  A depth-3 copy of NetworkAPISerializer would leave its declared net_type
  an ID. """
  class Meta:
    model = Network
    fields = '__all__'
    depth = 3

class NetworkTypeAPISerializer(serializers.ModelSerializer):
  """ A network type. """
  class Meta:
    model = NetworkType
    fields = '__all__'

class SwitchAPISerializer(serializers.ModelSerializer):
  # set from the request user by the UpdateSwitch pre_save signal.
  """ A switch; created_by and updated_by are read-only, set from the request. """
  created_by = serializers.PrimaryKeyRelatedField(read_only=True)
  updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
  network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False, allow_null=True)
  guid = GuidField(Switch)
  class Meta:
    model = Switch
    fields = '__all__'

class SwitchPortAPISerializer(serializers.ModelSerializer):
  """ A switch port. """
  switch = serializers.PrimaryKeyRelatedField(queryset=Switch.objects.all())
  networks = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all(), required=False, allow_null=True)

  class Meta:
    model = SwitchPort
    fields = '__all__'
