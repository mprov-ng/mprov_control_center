
from yaml import serialize
from django.conf import settings

from rest_framework import serializers
from .models import Network, Switch, NetworkType, SwitchPort

class NetworkAPISerializer(serializers.ModelSerializer):
  net_type = serializers.PrimaryKeyRelatedField(queryset=NetworkType.objects.all())
  class Meta:
    model = Network
    fields = '__all__'

class NetworkTypeAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = NetworkType
    fields = '__all__'

class SwitchAPISerializer(serializers.ModelSerializer):
  created_by = serializers.PrimaryKeyRelatedField(queryset=settings.AUTH_USER_MODEL.objects.all())
  network = serializers.PrimaryKeyRelatedField(queryset=Network.objects.all())
  class Meta:
    model = Switch
    fields = '__all__'

class SwitchPortAPISerializer(serializers.ModelSerializer):
  switch = serializers.PrimaryKeyRelatedField(queryset=Switch.objects.all())
  class Meta:
    model = SwitchPort
    fields = '__all__'