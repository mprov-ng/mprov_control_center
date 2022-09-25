from http.client import NETWORK_AUTHENTICATION_REQUIRED
from django.http import HttpResponseNotAllowed

from re import template
from unicodedata import name
from .serializers import (
    NetworkInterfaceDetailsSerializer,
    NetworkInterfaceSerializer,
    SystemSerializer,
    SystemGroupSerializer,
    SystemDetailSerializer,
    SystemBMCSerializer,
    SystemBMCDetailSerializer,
    SystemImageDetailsSerializer,
)
from rest_framework.response import Response

from common.views import MProvView
from systems.models import NetworkInterface, System, SystemGroup, SystemImage, SystemBMC, SystemModel
from rest_framework.response import Response
from networks.models import SwitchPort, Network, Switch
from rest_framework import generics
from jobqueue.models import Job, JobModule, JobStatus
from jobqueue.serializers import JobServerAPISerializer
from django.utils.text import slugify



class SystemRegAPIView(MProvView):
    '''
# /systems/register/

This is a special API Access point used by NADS.  It only accepts
POST methods, and they must be formatted in a specific way.

## Accepted HTTP Methods:
- POST (with NADS packet)


## Documentation

### POST method (with NADS Packet)
- This will register the mac in the packet, to the host that system
that has a NIC on the specified switch and port.
NADS Packet:


        {
            "vendor": The vendor associated with the system you which to register, must match what mPCC knows.
            "model": The model associated with the system you which to register, must match what mPCC knows.
            "switch": "some-switch-host-name", must match what mPCC knows.
            "port": "someport-number", must match what mPCC knows.
            "mac": "mac of the machine being registered"
        }

    '''
    model = System
    serializer_class = SystemSerializer
    queryset = System.objects.none()
    authentication_classes = [] #disables authentication
    permission_classes = [] #disables permission

    def get(self, request, *args, **kwargs):
        result = self.checkContentType(request, format=format)
        if result is not None:
            return result
        return HttpResponseNotAllowed(["POST"])

    def delete(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def put(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def patch(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, *args, **kwargs):
        print(request.data)
        
        switch = Switch.objects.get(hostname=request.data['switch'])
        print(switch)

        model_slug = slugify(f"{request.data['vendor']} {request.data['model']}")
        
        port= SwitchPort.objects.get(name=request.data['port'], switch=switch)
        print(port)
        nicQueryset = NetworkInterface.objects.all()
        nicQueryset = nicQueryset.filter(mac=None, switch_port=port)
        print(nicQueryset)
        if nicQueryset is not None and len(nicQueryset) > 0:
            system = System.objects.get(pk=nicQueryset[0].system.pk)
            print(model_slug)
            print(system)
            print(system.systemmodel.slug)
            if system.systemmodel.slug != model_slug:
                system=None
            if system is not None:
                nicObj = nicQueryset.first()
                nicObj.mac = request.data['mac']
                nicObj.save()
                # send in a pxe update job
                JobType = None
                try:
                    JobType = JobModule.objects.get(slug='pxe-update')
                except:
                    JobType = None
                print(JobType)
                # get or create the job module in the DB
                # get the jobtype, do nothing if it's not defined.
                if JobType is not None:
                    # save a new job, if one doesn't already exist.

                    Job.objects.update_or_create(
                    name=JobType.name , module=JobType,
                    defaults={'status': JobStatus.objects.get(pk=1)}
                    ) 
                # return the system object.    
                self.queryset = [system]
                return  generics.ListAPIView.get(self, request, format=None)
        # return 404
        #self.queryset = []
        # TODO insert MAC ban code here if needed.
        return Response(None, status=404)
        # pass
        # return  generics.ListAPIView.get(self, request, format=None)

class SystemAPIView(MProvView):
    '''
# /systems/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /systems/1/)
- POST (with primary key, ie: /systems/1/)
- PATCH (with primary key, ie: /systems/1/)
- DELETE (with primary key, ie: /systems/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- hostname: The hostname of the server
- timestamp: The creation time of the entry
- created_by: The user who created this entry
- updated: Timestamp of the last update
- systemgroups: array of system group ID's
- config_params: The configuration parameters for this entry
- systemimage: The ID of the system image.

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:


    [
    {
        "id": 1,
        "hostname": "compute001",
        "timestamp": "2022-05-10T15:40:30.804398-05:00",
        "updated": "2022-05-17T13:56:34.523913-05:00",
        "config_params": "",
        "created_by": 1,
        "systemimage": "compute",
        "systemgroups": [
        2
        ],
        "scripts": []
    },
    {
        "id": 2,
        "hostname": "compute002",
        "timestamp": "2022-05-13T09:38:58.211597-05:00",
        "updated": "2022-05-23T16:00:11.526715-05:00",
        "config_params": "-- #Inherit from System Group or Distrubtion.",
        "created_by": 1,
        "systemimage": "compute",
        "systemgroups": [
        2
        ],
        "scripts": []
    }
    ]



### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified with a retrieval depth of 3 or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = System
    template = "systems_docs.html"
    serializer_class = SystemDetailSerializer
    queryset = None

    def post(self, request, *args, **kwargs):
        if 'self' in request.query_params:
            # someone would like modify themselves.
            # grab the IP
            ip=""
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            # for testing
            ip="172.16.12.1"
            nicQueryset = NetworkInterface.objects.all()
            nicQueryset = nicQueryset.filter(ipaddress=ip)
            if nicQueryset.count() == 0:
                return Response(None, status=404)
            system = nicQueryset[0].system
            print(system)
            for arg in request.data:
                if arg == "netboot":
                    # we should only be working on disabling netboot.
                    nicQueryset = NetworkInterface.objects.all()
                    nicQueryset = nicQueryset.filter(system=system)
                    for nic in nicQueryset:
                        nic.bootable = False
                        nic.save()
                else:
                    # Unsupported, return 403 forbidden
                    return Response(None, status=403)
            # done with the for loop, return status 200
            return Response(None, status=200)

        
        return super().post(request, *args, **kwargs)
    def get(self, request, format=None, **kwargs):
        super().get(request, format=None, **kwargs)
        # result = self.checkContentType(request, format=format, kwargs=kwargs)
        # if result is not None:
        #     return result
        # if self.model == None:
        #     return Response(None)
        # if 'pk' in kwargs:
        #     # someone is looking for a specific item.
        #     return self.retrieve(self, request, format=None, pk=kwargs['pk'])
        # self.serializer_class = SystemSerializer
        # self.queryset = self.model.objects.all()
        # if 'hostname' in request.query_params:
        #     # someone is looking for a specific item.
        #     self.queryset = self.queryset.filter(hostname=request.query_params['hostname'])
        #     if self.queryset.count() == 0:
        #         return Response(None, status=404)
        if 'self' in request.query_params:
            # someone would like us to tell them who they are.
            # grab the IP
            ip=""
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            # for testing
            #ip="172.16.12.1"
            
            # now try to grab the nic for this IP
            nicQueryset = NetworkInterface.objects.all()
            nicQueryset = nicQueryset.filter(ipaddress=ip)
            if nicQueryset.count() == 0:
                return Response(None, status=404)
            # self.model = Network
            # self.serializer_class = NetworkInterfaceDetailsSerializer
            self.queryset = self.queryset.filter(pk=nicQueryset[0].system.id)
            self.serializer_class = SystemDetailSerializer

            # return self.retrieve(self, request, format=None,pk=nicQueryset[0].system.id)

        return generics.ListAPIView.get(self, request, format=None)

class SystemGroupAPIView(MProvView):
    '''
# /systemgroups/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /systemgroups/1/)
- POST (with primary key, ie: /systemgroups/1/)
- PATCH (with primary key, ie: /systemgroups/1/)
- DELETE (with primary key, ie: /systemgroups/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: The name of the system group
- config_params: The configuration parameters for this entry
- scripts: A list of scripts that will run on this group

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:


    [
    {
        "id": 2,
        "name": "compute",
        "config_params": "extra_packages: 
            - vim-enhanced
            - wget
            - epel-release
            - tmux",
        "scripts": [
            "extra_packagessh"
        ]
    },
    {
        "id": 1,
        "name": "login",
        "config_params": "-- # Inherit from OS",
        "scripts": []
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
    model = SystemGroup
    template = "systemgroup_docs.html"
    serializer_class = SystemGroupSerializer

class NetworkInterfaceAPIView(MProvView):
    '''
# /networkinterfaces/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /networkinterfaces/1/)
- POST (with primary key, ie: /networkinterfaces/1/)
- PATCH (with primary key, ie: /networkinterfaces/1/)
- DELETE (with primary key, ie: /networkinterfaces/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: The name of the interface
- hostname: The hostname for this interface to be registered to DNS/DHCP
- ipaddress: The IP address to be registered to DNS/DHCP for this interface
- bootable: Is this NIC bootable?
- system: The system ID this NIC is associated with
- switch_port: The switch port ID this NIC is connected to.

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:


    [
    {
        "id": 1,
        "name": "eno1",
        "hostname": "compute001",
        "ipaddress": "172.16.30.1",
        "mac": "4c:d9:8f:3c:f5:ae",
        "bootable": true,
        "system": 1,
        "switch_port": 3
    },
    {
        "id": 2,
        "name": "eno1",
        "hostname": "compute002",
        "ipaddress": "172.16.30.2",
        "mac": "4c:d9:8f:3b:79:d9",
        "bootable": true,
        "system": 2,
        "switch_port": 2
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
    model = NetworkInterface
    template = "networkinterface_docs.html"
    serializer_class = NetworkInterfaceSerializer
    def get(self, request, format=None, **kwargs):
        super().get(request, format=None, **kwargs)
        
        if 'network' in self.request.query_params:
            network = self.request.query_params['network']
            # get the Network ID
            print(network)
            net = Network.objects.filter(slug=network)
            print(net)
            innerQ = SwitchPort.objects.filter(networks__in=net)
            self.queryset = self.queryset.filter(switch_port__in=innerQ)
        
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None)


class NetworkInterfaceDetailAPIView(MProvView):
      model = NetworkInterface
      template = "networkinterface_docs.html"
      serializer_class = NetworkInterfaceDetailsSerializer


class SytemImagesAPIView(MProvView):
    
    '''
# /systemimages/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /systemimages/compute/)
- POST (with primary key, ie: /systemimages/compute/)
- PATCH (with primary key, ie: /systemimages/compute/)
- DELETE (with primary key, ie: /systemimages/compute/)

## Documentation

### Class Attributes
- slug: a machine parsable version of the name
- name: A human readable name
- timestamp: (Optional) The time this entry was created
- created_by: The User that is creating this 
- updated: (Auto) The time this entry was last updated
- systemgroups: Array of system groups this system image is a part of
- needs_rebuild: If the user is asking to rebuild this image.
- version: used internally for tracking when an image changes
- jobservers: array of jobservers actively serving this version of this image.
- config_params: YAML of config parameters set on this system image, used by scripts
- osddistro: the distro to base this image off of.
- osrepos: (Optional) extra repos for this image.

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:

    [
    {
        "slug": "nads",
        "name": "__nads__",
        "timestamp": "2022-05-13T07:55:11.100467-05:00",
        "updated": "2022-05-16T15:21:09.903630-05:00",
        "needs_rebuild": false,
        "version": 12,
        "config_params": "extra_packages:
            - vim-enhanced
            - wget
            - curl
            - epel-release
            - tcpdump",
        "created_by": 1,
        "osdistro": 1,
        "systemgroups": [],
        "scripts": [
        "extra_packagessh",
        "nadssh",
        "set_root_pwsh"
        ],
        "jobservers": [
        3
        ],
        "osrepos": []
    },
    {
        "slug": "compute",
        "name": "compute",
        "timestamp": "2022-05-10T11:55:51.419198-05:00",
        "updated": "2022-05-12T16:20:51.588620-05:00",
        "needs_rebuild": false,
        "version": 7,
        "config_params": "- rootpw: '$6$80Lz0whR9xNVPouX$L3wyFx7h3oYS9RvzFTVJLFUkjApUCJ3kH5KtOUZgREMEDp7owSxVq5NlFCcR9s3knaz7g4YuCXBiqcbQJGRl91'",
        "created_by": 1,
        "osdistro": 1,
        "systemgroups": [
        2
        ],
        "scripts": [],
        "jobservers": [
        3
        ],
        "osrepos": [
        1
        ]
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified, with retrieval depth of 3 or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.


    '''
    model = SystemImage
    queryset = SystemImage.objects.all()
    serializer_class = SystemImageDetailsSerializer
    jobservers=JobServerAPISerializer(many=True)
    
    # def get(self, request, format=None, **kwargs):
    #     return self.retrieve(self, request, format=None, **kwargs)


# class SytemImageUpdateAPIView(MProvView):
#   model = SystemImage
#   queryset = SystemImage.objects.all()
#   serializer_class = SystemImageUpdateSerializer
 

class SystemBMCAPIView(MProvView):
    '''
# /systembmcs/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /systembmcs/1/)
- POST (with primary key, ie: /systembmcs/1/)
- PATCH (with primary key, ie: /systembmcs/1/)
- DELETE (with primary key, ie: /systembmcs/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- ipaddress: The IP of the entry
- mac: The MAC address of the entry
- username: The username for authentication with this entry
- password: The pwassword for authentication with this entry
- system: ID of the system this entry is associated with.
- switch_port: ID of the switchport this entry resides on.

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:


    [
    {
        "id": 1,
        "ipaddress": "172.16.20.1",
        "mac": null,
        "username": null,
        "password": null,
        "system": 1,
        "switch_port": null
    }
    ]


### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified with a retrieval depth of 3 or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = SystemBMC
    template = "systems_docs.html"
    serializer_class = SystemBMCDetailSerializer
    queryset = None
    # def get(self, request, format=None, **kwargs):
       
    #     result = self.checkContentType(request, format=format, kwargs=kwargs)
    #     if result is not None:
    #         return result
    #     if self.model == None:
    #         return Response(None)
    #     if 'pk' in kwargs:
    #         # someone is looking for a specific item.
    #         return self.retrieve(self, request, format=None, pk=kwargs['pk'])
    #     self.serializer_class = SystemBMCSerializer
    #     self.queryset = self.model.objects.all()
    #     if 'hostname' in request.query_params:
    #         # someone is looking for a specific item.
    #         queryset = self.queryset.filter(hostname=request.query_params['hostname'])
    #         if queryset.count() == 0:
    #             return Response(None, status=404)
    #     return generics.ListAPIView.get(self, request, format=None)
