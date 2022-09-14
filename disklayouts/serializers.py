
from dataclasses import field
from rest_framework import serializers

from .models import DiskLayout, DiskPartition, RaidLayout
from systems.models import *

class DiskPartitionAPISerializer(serializers.ModelSerializer):
  disklayout = serializers.PrimaryKeyRelatedField(queryset=DiskLayout.objects.all())
  class Meta:
    model = DiskPartition
    fields = '__all__'
    depth=2


class  RaidLayoutAPISerializer(serializers.ModelSerializer):
  systems = serializers.PrimaryKeyRelatedField(queryset=System.objects.all(), many=True)

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
  systems = serializers.PrimaryKeyRelatedField(queryset=System.objects.all(), many=True)
  partitions = DiskPartitionAPISerializer(many=True, read_only=True)
  members = serializers.SerializerMethodField("getMembers")
  filesystem = serializers.SerializerMethodField("getRaidFS")
  raidlevel = serializers.SerializerMethodField("getRaidLevel")
  mount = serializers.SerializerMethodField("getMount")
  class Meta:
      model = DiskLayout
      fields = ['name', 'slug', 'diskname','partitions','dtype', 'members', 'filesystem', 'raidlevel', 'mount']
      depth = 6
  def getMount(self, obj):
    if obj.dtype == DiskLayout.DiskTypes.MDRD:
      rlayout = RaidLayout.objects.all()
      rlayout = rlayout.filter(slug=obj.slug)
      return rlayout[0].mount
    return None
  def getMembers(self, obj):
    if obj.dtype == DiskLayout.DiskTypes.MDRD:
      # we have a raid layout
      rlayout = RaidLayout.objects.all()
      rlayout = rlayout.filter(slug=obj.slug)
      serializer = DiskPartitionAPISerializer(rlayout[0].partition_members.all(), many=True)
      return serializer.data
    return None

  def getRaidLevel(self, obj):
    if obj.dtype == DiskLayout.DiskTypes.MDRD:
      rlayout = RaidLayout.objects.all()
      rlayout = rlayout.filter(slug=obj.slug)
      return rlayout[0].raidlevel
      # return serializer.data
    return None

  def getRaidFS(self, obj):
    if obj.dtype == DiskLayout.DiskTypes.MDRD:
      rlayout = RaidLayout.objects.all()
      rlayout = rlayout.filter(slug=obj.slug)
      return rlayout[0].filesystem
      # return serializer.data

    return None