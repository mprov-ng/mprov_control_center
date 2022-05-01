from http.client import NETWORK_AUTHENTICATION_REQUIRED
from re import template
from .serializers import NetworkInterfaceDetailsSerializer, NetworkInterfaceSerializer

from common.views import MProvView
from systems.models import NetworkInterface, System, SystemGroup, SystemImage
from django.shortcuts import render
from rest_framework.response import Response
from django.db.models import Prefetch
from networks.models import SwitchPort, Network
from rest_framework import status, generics



class SystemAPIView(MProvView):
      model = System
      template = "systems_docs.html"
      
class SystemGroupAPIView(MProvView):
      model = SystemGroup
      template = "systemgroup_docs.html"

class NetworkInterfaceAPIView(MProvView):
      model = NetworkInterface
      template = "networkinterface_docs.html"
      serializer_class = NetworkInterfaceSerializer
      def get(self, request, format=None, **kwargs):
        if(request.content_type != 'application/json'):
            return render(request, self.template, {})
        # if we are 'application/json' return an empty dict if
        # model is not set.
        if self.model == None:
            return Response(None)
        
        if 'pk' in kwargs:
            # someone is looking for a specific item.
            return self.retrieve(self, request, format=None, pk=kwargs['pk'])

        # Let's see if someone is looking for something specific.
        queryset = self.model.objects.all()
        network = self.request.query_params.get('network')
        print(network)
        if network is not None:
            # get the Network ID
            net = Network.objects.filter(slug=network)
            innerQ = SwitchPort.objects.filter(networks__in=net)
            queryset = self.model.objects.filter(switch_port__in=innerQ)
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);


class NetworkInterfaceDetailAPIView(MProvView):
      model = NetworkInterface
      template = "networkinterface_docs.html"
      serializer_class = NetworkInterfaceDetailsSerializer


