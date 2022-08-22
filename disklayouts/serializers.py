
from rest_framework import serializers

from .models import DiskLayout, DiskPartition

class DiskPartitionAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = DiskPartition
    fields = '__all__'

class DiskLayoutAPISerializer(serializers.ModelSerializer):

  partitions = DiskPartitionAPISerializer(many=True, read_only=True)
  class Meta:
      model = DiskLayout
      fields = ['name', 'slug', 'diskname','partitions']
      depth = 3