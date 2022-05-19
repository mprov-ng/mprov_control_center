
from yaml import serialize

from rest_framework import serializers
from .models import Network, Switch, NetworkType, SwitchPort

class NetworkAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = Network
    fields = '__all__'

class NetworkTypeAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = NetworkType
    fields = '__all__'

class SwitchAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = Switch
    fields = '__all__'

class SwitchPortAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = SwitchPort
    fields = '__all__'