from http.client import NETWORK_AUTHENTICATION_REQUIRED
from re import template
from common.views import MProvView
from systems.models import NetworkInterface, System, SystemGroup


class SystemAPIView(MProvView):
      model = System
      template = "systems_docs.html"
      
class SystemGroupAPIView(MProvView):
      model = SystemGroup
      template = "systemgroup_docs.html"

class NetworkInterfaceAPIView(MProvView):
      model = NetworkInterface
      template = "networkinterface_docs.html"
