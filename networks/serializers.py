
from yaml import serialize

from rest_framework import serializers
from .models import Network, Switch

class NetworkAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = Network
    fields = '__all__'

class SwitchAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = Switch
    fields = '__all__'