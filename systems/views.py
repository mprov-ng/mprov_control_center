from http.client import NETWORK_AUTHENTICATION_REQUIRED
import ipaddress
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

class IPXEAPIView(MProvView):
    model = NetworkInterface
    serializer_class = NetworkInterfaceDetailsSerializer
    authentication_classes = [] #disables authentication
    permission_classes = [] #disables permission
    def get(self, request, format=None, **kwargs):
        # grab the IP
        ip=""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        ip="172.16.0.1"
        # now try to grab the nic for this IP
        queryset = self.model.objects.all()
        queryset = queryset.filter(ipaddress=ip)
        context= {
            'nics': queryset,
        }
        print(ip)
        print(context['nics'])
        return(render(template_name="ipxe", request=request, context=context, content_type="text/plain" ))
        pass

