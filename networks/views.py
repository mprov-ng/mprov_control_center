
from common.views import MProvView
from networks.models import Network, NetworkType, Switch, SwitchPort
from .serializers import (
    NetworkAPISerializer, 
    SwitchAPISerializer, 
    NetworkTypeAPISerializer, 
    SwitchPortAPISerializer,
)
from rest_framework.response import Response
from rest_framework import generics


class NetworkAPIView(MProvView):
    '''
# /networks/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /networks/1/)
- POST (with primary key, ie: /networks/1/)
- PATCH (with primary key, ie: /networks/1/)
- DELETE (with primary key, ie: /networks/1/)

## Documentation

### Class Attributes
- id: The internal ID of the network in the db
- name: A human readable name for the network
- net_type: The ID of the network Type for this network.
- slug: (Optional, generated) a machine parsable version of the network name
- vlan: (Optional) a descriptor of the vlan.
- subnet: The subnet for this network
- netmask: The CIDR notation numeric mask
- gateway: (Optional) The gateway for this network.
- nameserver1: (Optional) The First nameserver for this network.
- domain: (Optional) A domain name to be associated with this network
- isdhcp: (Default: False) Should mProv mananage DHCP?
- managedns: (Default: False) Should mProv manage DNS?
- isbootable: (Default: False) Is this a PXE/BootP/Net Boot network?
- dhcpstart: (Optional) The staring IP of the DHCP Range for non-associated hosts.
- dhcpend: (Optional) The ending IP of the DHCP Rnage. 

### GET method (no parameters)
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

### GET, POST, PATCH, DELETE (with primary key)
    - These methods, when passed a primary key, will Retrieve, Create, Update, or 
      Delete that entry in the database.  POST requires ALL required fields.  PATCH
      will only update the fields passed, required fields can be omitted if changed.
    
    - GET returns the object specified or 404

    - POST returns the new object created or a 500 style error

    - PATCH returns the updated object.

    - DELETE returns 204 No Content if the delete is successful.

    '''
    model = Network 
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
        if isdhcp is not None:
            queryset = queryset.filter(isdhcp=isdhcp)

        
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);

class NetworkTypeAPIView(MProvView):
    '''
# /networktypes/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /networktypess/1/)
- POST (with primary key, ie: /networktypes/1/)
- PATCH (with primary key, ie: /networktypes/1/)
- DELETE (with primary key, ie: /networktypes/1/)

## Documentation

### Class Attributes
- id: The internal ID of the network type in the db
- name: A human readable name for the network type
- description: (Optional) A human readable explanation of this network type

### GET method (no parameters)
Returns a json list of all networktypes in the MPCC

Format returned:

    [
    {
        "id": 1,
        "name": "Ethernet",
        "description": ""
    },
    {
        "id": 2,
        "name": "Infiniband",
        "description": ""
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
    - These methods, when passed a primary key, will Retrieve, Create, Update, or 
      Delete that entry in the database.  POST requires ALL required fields.  PATCH
      will only update the fields passed, required fields can be omitted if changed.
    
    - GET returns the object specified or 404

    - POST returns the new object created or a 500 style error

    - PATCH returns the updated object.

    - DELETE returns 204 No Content if the delete is successful.

    '''
    model = NetworkType
    serializer_class = NetworkTypeAPISerializer

class SwitchAPIView(MProvView):
    model = Switch
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
        # print(network)
        if network is not None:
            net = Network.objects.get(slug=network)
            queryset = self.model.objects.filter(network=net)
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);

class SwitchPortAPIView(MProvView):
    model = SwitchPort
    serializer_class = SwitchPortAPISerializer