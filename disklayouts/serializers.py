
from dataclasses import field
from rest_framework import serializers

from .models import DiskLayout, DiskPartition, RaidLayout

class DiskPartitionAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = DiskPartition
    fields = '__all__'


class  RaidLayoutAPISerializer(serializers.ModelSerializer):
  class Meta:
    model = RaidLayout
    fields = '__all__'
    depth = 1
  # def __init__(self, *args, **kwargs):
  #   if 'membersOnly' in kwargs:
  #     self.fields = ('partition_members', )
  #     kwargs.pop('membersOnly')
  #   super().__init__(*args, **kwargs)

class DiskLayoutAPISerializer(serializers.ModelSerializer):

  partitions = DiskPartitionAPISerializer(many=True, read_only=True)
  members = serializers.SerializerMethodField("getMembers")
  class Meta:
      model = DiskLayout
      fields = ['name', 'slug', 'diskname','partitions','dtype', 'members']
      depth = 3

  def getMembers(self, obj):
    request = self.context.get('request')
    serializer_context = {'request': request }
    if obj.dtype == DiskLayout.DiskTypes.MDRD:
      # we have a raid layout
      rlayout = RaidLayout.objects.all()
      rlayout = rlayout.filter(slug=obj.slug)
      serializer = DiskPartitionAPISerializer(rlayout[0].partition_members.all(), many=True)
      return serializer.data
    return None

