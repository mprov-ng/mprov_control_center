
from yaml import serialize

from rest_framework import serializers
from .models import Network

class NetworkAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = Network
    fields = '__all__'