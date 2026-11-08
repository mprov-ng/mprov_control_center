from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import get_resolver
from rest_framework import serializers

from networks.models import Network, NetworkType, Switch, SwitchPort
from systems.models import NetworkInterface, System, SystemGroup, SystemImage


def api_views(resolver=None, prefix=""):
  """ (route, view class) for every URL pattern served by a DRF view. """
  resolver = resolver or get_resolver()
  for pattern in resolver.url_patterns:
    if hasattr(pattern, "url_patterns"):
      yield from api_views(pattern, prefix + str(pattern.pattern))
    else:
      cls = getattr(pattern.callback, "cls", None) or getattr(pattern.callback, "view_class", None)
      if cls is not None and hasattr(cls, "get_serializer_class"):
        yield prefix + str(pattern.pattern), cls


def nested_users(serializer, path, found, depth=0):
  """ Add to found every field path under serializer that renders a nested user. """
  for name, field in serializer.fields.items():
    child = getattr(field, "child", None) or getattr(field, "child_relation", None) or field
    if not isinstance(child, serializers.BaseSerializer):
      continue
    if getattr(getattr(child, "Meta", None), "model", None) is get_user_model():
      found.append(f"{path}.{name}")
    elif depth < 6:
      nested_users(child, f"{path}.{name}", found, depth + 1)


class NoSerializerNestsUsersTests(SimpleTestCase):
  """ No API view, with or without ?detail, renders a nested user record; a
  related user is its ID. """

  def test_no_view_nests_a_user(self):
    from common.views import depth3_serializer
    found = []
    for route, cls in api_views():
      candidates = []
      if getattr(cls, "serializer_class", None):
        candidates.append(cls.serializer_class)
        if hasattr(cls, "serve_detail") and not getattr(cls, "detail_serializer_class", None):
          candidates.append(depth3_serializer(cls.serializer_class))
      if getattr(cls, "detail_serializer_class", None):
        candidates.append(cls.detail_serializer_class)
      for serializer_class in candidates:
        nested_users(serializer_class(), f"/{route} {serializer_class.__name__}", found)
    self.assertEqual(found, [])


class DetailResponsesTests(TestCase):
  """ Detail responses give a related user as its ID. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    net_type = NetworkType.objects.create(name="Ethernet")
    network = Network.objects.create(name="lan", net_type=net_type, subnet="10.77.0.0", netmask=24)
    switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.77.0.250", mgmt_mac="de:ad:be:ef:77:01",
                                   created_by=self.user)
    port = SwitchPort.objects.create(name="1/1", switch=switch, networks=network)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.system = System.objects.create(hostname="c01", created_by=self.user, systemimage=self.image)
    self.nic = NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.77.0.11",
                                               mac="aa:bb:cc:77:00:11", switch_port=port, network=network)
    self.group = SystemGroup.objects.create(name="rack1")
    self.group.systems.add(self.system)

  def get(self, url):
    response = self.client.get(url, CONTENT_TYPE="application/json", REMOTE_ADDR="10.77.0.11")
    self.assertEqual(response.status_code, 200, url)
    data = response.json()
    return data[0] if isinstance(data, list) else data

  def test_systems(self):
    for url in ("/systems/?self", "/systems/?detail", f"/systems/{self.system.pk}/",
                f"/systems/{self.system.pk}/?detail"):
      system = self.get(url)
      self.assertEqual(system["created_by"], self.user.pk, url)
      # the image is still nested, only the user isn't.
      self.assertEqual(system["systemimage"]["created_by"], self.user.pk, url)

  def test_system_images(self):
    for url in ("/systemimages/?detail", f"/systemimages/{self.image.slug}/",
                f"/systemimages/{self.image.slug}/details"):
      self.assertEqual(self.get(url)["created_by"], self.user.pk, url)

  def test_system_groups(self):
    for url in ("/systemgroups/?detail", f"/systemgroups/{self.group.pk}/"):
      group = self.get(url)
      self.assertEqual(group["systems"][0]["created_by"], self.user.pk, url)

  def test_network_interfaces(self):
    for url in ("/networkinterfaces/?detail", f"/networkinterfaces/{self.nic.pk}/"):
      nic = self.get(url)
      self.assertEqual(nic["system"]["created_by"], self.user.pk, url)
      self.assertEqual(nic["switch_port"]["switch"]["created_by"], self.user.pk, url)
