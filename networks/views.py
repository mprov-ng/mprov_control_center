
from django.http import HttpResponseNotAllowed
from common.views import MProvView
from networks.models import Network, NetworkType, Switch, SwitchPort
from .serializers import NetworkAPISerializer, SwitchAPISerializer
from rest_framework import mixins
from rest_framework.response import Response
from django.shortcuts import render
from rest_framework import status, generics


class NetworkAPIView(MProvView,mixins.RetrieveModelMixin):
    '''
# /networks/

## Accepted HTTP Methods:
- get

## Documentation

### get method
Returns a json list of all networks in the MPCC

Format returned:


    [
        {
            "id": 1,
            "name": "Cluster LAN",
            "slug": "cluster-lan",
            "vlan": "default",
            "subnet": "172.16.0.0",
            "netmask": 16,
            "gateway": "172.16.1.1",
            "nameserver1": "172.16.1.1",
            "domain": "test.cluster",
            "isdhcp": true,
            "managedns": true,
            "isbootable": true,
            "dhcpstart": "172.16.254.1",
            "dhcpend": "172.16.254.254",
            "net_type": 1
        }
    ]

    '''
    model = Network 
    template = 'network_docs.html'
    serializer_class = NetworkAPISerializer

    # Override the default get func, we need a bit more specialized query here
    def get(self, request, format=None, **kwargs):
        result = self.checkContentType(request, format=format, kwargs=kwargs)
        if result is not None:
            return result
        # if we are 'application/json' return an empty dict if
        # model is not set.
        if self.model == None:
            return Response(None)
        
        if 'pk' in kwargs:
            # someone is looking for a specific item.
            return self.retrieve(self, request, format=None, pk=kwargs['pk'])

        # Let's see if someone is looking for something specific.
        queryset = self.model.objects.all()
        isdhcp = self.request.query_params.get('isdhcp')
        # print(jobmodule)
        if isdhcp is not None:
            queryset = queryset.filter(isdhcp=isdhcp)

        
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);

    def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

    def delete(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])
    
    def put(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

    def patch(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

class NetworkTypeAPIView(MProvView):
    model = NetworkType
    template = 'networktype_docs.html'

class SwitchAPIView(MProvView):
    model = Switch
    template = 'switch_docs.html'
    serializer_class = SwitchAPISerializer

    def get(self, request, format=None, **kwargs):
        result = self.checkContentType(request, format=format, kwargs=kwargs)
        if result is not None:
            return result
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
            net = Network.objects.get(slug=network)
            queryset = self.model.objects.filter(network=net)
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);

class SwitchPortAPIView(MProvView):
    model = SwitchPort
    template = 'switchport_docs.html'
    