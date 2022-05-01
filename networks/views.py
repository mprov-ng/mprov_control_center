
from common.views import MProvView
from networks.models import Network, NetworkType, Switch, SwitchPort
from .serializers import NetworkAPISerializer

class NetworkAPIView(MProvView):
    model = Network 
    template = 'network_docs.html'
    serializer_class = NetworkAPISerializer

class NetworkTypeAPIView(MProvView):
    model = NetworkType
    template = 'networktype_docs.html'

class SwitchAPIView(MProvView):
    model = Switch
    template = 'switch_docs.html'

class SwitchPortAPIView(MProvView):
    model = SwitchPort
    template = 'switchport_docs.html'
