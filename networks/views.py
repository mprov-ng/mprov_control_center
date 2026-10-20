
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
- GET (with Primary Key, e.g. /networks/1/)
- POST (no primary key, e.g. /networks/)
- PATCH (with primary key, e.g. /networks/1/)
- DELETE (with primary key, e.g. /networks/1/)

## Documentation

### Class Attributes
- id: The internal ID of the network in the db
- name: A human-readable name for the network
- net_type: The ID of the network type for this network.
- slug: (Optional, generated) a machine-parsable version of the network name
- vlan: (Optional, Default: 0) The integer VLAN ID.
- subnet: The subnet for this network
- netmask: The CIDR notation numeric mask
- gateway: (Optional) The gateway for this network.
- nameserver1: (Optional) The primary nameserver for this network.
- domain: (Optional) A domain name to be associated with this network
- isdhcp: (Default: False) Should mProv manage DHCP?
- managedns: (Default: False) Should mProv manage DNS?
- isbootable: (Default: False) Is this a PXE/BootP/Net Boot network?
- dhcpstart: (Optional) The starting IP of the DHCP range for non-associated hosts.
- dhcpend: (Optional) The ending IP of the DHCP range. 

### GET method (no parameters)
Returns a JSON list of all networks in the mPCC.  The list can be filtered
with the optional ?isdhcp= and ?managedns= query parameters (true/false in any
case, or 1/0), and by any other field with ?FIELD=VALUE (exact match).  An
invalid filter returns 400; no matches returns an empty list.

Format returned:


    [
        {
            "id": 1,
            "name": "Cluster LAN",
            "slug": "cluster-lan",
            "vlan": 0,
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

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST, sent to the collection URL with no
    primary key, will Create a new entry and requires ALL required fields.  PATCH
    will only update the fields passed; required fields can be omitted if unchanged.

- GET returns the object specified or 404

- POST returns the new object created, or 400 with the validation errors

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
        # if we are 'application/json' return an empty 200 response if
        # model is not set.
        if self.model is None:
            return Response(None)
        
        if 'pk' in kwargs:
            # someone is looking for a specific item.
            return self.retrieve(request, pk=kwargs['pk'])

        # Let's see if someone is looking for something specific.
        queryset, error_body = self.filter_by_query_params(request, kwargs, skip=('isdhcp', 'managedns'))
        for field in ('isdhcp', 'managedns'):
            value = self.request.query_params.get(field)
            if value is None:
                continue
            value = {'true': True, '1': True, 'false': False, '0': False}.get(value.lower())
            if value is None:
                error_body[field] = f"{field} must be true, false, 1 or 0."
            else:
                queryset = queryset.filter(**{field: value})
        if len(error_body) > 0:
            return Response(error_body, status=400)
        self.queryset=queryset
        # return the super call for get.  No match is an empty list, not 404:
        # the jobserver's dnsmasq plugins loop over this list.
        return generics.ListAPIView.get(self, request, format=None)

class NetworkTypeAPIView(MProvView):
    '''
# /networktypes/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, e.g. /networktypes/1/)
- POST (no primary key, e.g. /networktypes/)
- PATCH (with primary key, e.g. /networktypes/1/)
- DELETE (with primary key, e.g. /networktypes/1/)

## Documentation

### Class Attributes
- id: The internal ID of the network type in the db
- name: A human-readable name for the network type
- description: (Optional) A human-readable explanation of this network type

### GET method (no parameters)
Returns a JSON list of all network types in the mPCC

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

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST, sent to the collection URL with no
    primary key, will Create a new entry and requires ALL required fields.  PATCH
    will only update the fields passed; required fields can be omitted if unchanged.

- GET returns the object specified or 404

- POST returns the new object created, or 400 with the validation errors

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = NetworkType
    serializer_class = NetworkTypeAPISerializer

class SwitchAPIView(MProvView):
    '''
# /switches/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, e.g. /switches/1/)
- POST (no primary key, e.g. /switches/)
- PATCH (with primary key, e.g. /switches/1/)
- DELETE (with primary key, e.g. /switches/1/)

## Documentation

### Class Attributes
- id: Internal ID of this switch in the db
- hostname: hostname of this switch
- timestamp: (Default: now) Creation time for this switch
- updated: (Default: now) Last update time for this switch (not changed automatically on save)
- mgmt_ip: The IP Address of the management interface for this switch
- mgmt_mac: The MAC address of the management interface for this switch
- created_by: The user who last saved this switch (set automatically on every save)
- network: (Optional) ID of the management network for this switch.

### Query Parameters
- ?network=SLUG: GET only returns switches on the network with that slug, or 404 if
    there is no such network.  A network with no switches returns an empty list.
- ?FIELD=VALUE: GET (no primary key) only returns entries where that field matches exactly.
    Without ?network=, an empty result returns 404.

### GET method (no parameters)
Returns a JSON list of all objects of this type in the mPCC

Format returned:

    [
    {
        "id": 1,
        "hostname": "office-pop-rack7",
        "timestamp": "2022-05-10T15:48:34.403983-05:00",
        "updated": "2022-05-19T15:58:21.610109-05:00",
        "mgmt_ip": "172.16.253.1",
        "mgmt_mac": "de:ad:be:ef:01:02",
        "created_by": 1,
        "network": 1
    }
    ]

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST, sent to the collection URL with no
    primary key, will Create a new entry and requires ALL required fields.  PATCH
    will only update the fields passed; required fields can be omitted if unchanged.

- GET returns the object specified or 404

- POST returns the new object created, or 400 with the validation errors

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = Switch
    serializer_class = SwitchAPISerializer

    def get(self, request, format=None, **kwargs):
        if 'pk' in kwargs or 'network' not in request.query_params:
            return super().get(request, format=format, **kwargs)

        # ?network= takes a network slug, which the base class can't filter on.
        result = self.checkContentType(request, format=format)
        if result is not None:
            return result
        net = Network.objects.filter(slug=request.query_params['network']).first()
        if net is None:
            return Response(None, status=404)
        self.queryset, error_body = self.filter_by_query_params(request, kwargs, skip=('network',))
        if len(error_body) > 0:
            return Response(error_body, status=400)
        self.queryset = self.queryset.filter(network=net)

        # A network with no switches returns an empty list, not 404: the
        # jobserver's dnsmasq plugins add this list to their host lists.
        return generics.ListAPIView.get(self, request, format=None)

class SwitchPortAPIView(MProvView):
    '''
# /switchports/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, e.g. /switchports/1/)
- POST (no primary key, e.g. /switchports/)
- PATCH (with primary key, e.g. /switchports/1/)
- DELETE (with primary key, e.g. /switchports/1/)

## Documentation

### Class Attributes
- id: Internal ID of this port in the db
- name: A human-readable name for the port number
- switch: ID of the switch this port is associated with
- networks: ID of the network for this port.
    
### GET method (no parameters)
Returns a JSON list of all objects of this type in the mPCC

Format returned:

    [
    {
        "id": 1,
        "name": "1",
        "switch": 1,
        "networks": 1
    },
    {
        "id": 2,
        "name": "32",
        "switch": 1,
        "networks": 1
    },
    {
        "id": 3,
        "name": "31",
        "switch": 1,
        "networks": 1
    }
    ]

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST, sent to the collection URL with no
    primary key, will Create a new entry and requires ALL required fields.  PATCH
    will only update the fields passed; required fields can be omitted if unchanged.

- GET returns the object specified or 404

- POST returns the new object created, or 400 with the validation errors

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = SwitchPort
    serializer_class = SwitchPortAPISerializer