import subprocess
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from .serializers import (
    NetworkInterfaceDetailsSerializer,
    NetworkInterfaceSerializer,
    SystemSerializer,
    SystemGroupSerializer,
    SystemBMCSerializer,
    SystemBMCDetailSerializer,
    SystemImageDetailsSerializer,
    SystemDetailSerializer,
    SystemImageSerializer,
)
from rest_framework.response import Response

from common.views import MProvView
from systems.models import NetworkInterface, System, SystemGroup, SystemImage, SystemBMC, NADSSystem
from rest_framework.response import Response
from networks.models import SwitchPort, Network, Switch
from rest_framework import generics
from jobqueue.models import Job, JobModule, JobStatus
from jobqueue.serializers import JobServerAPISerializer
from django.utils.text import slugify
import pyipmi
import pyipmi.interfaces
from func_timeout import func_timeout, FunctionTimedOut

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
            "mac": mac of the machine being registered
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

    def mac2LL(self, mac=None):
        if mac == None:
            return None
        mac_octets = mac.split(":")
        # take the first octet and invert the 2nd to last bit.
        mac_octets[0] = "%X" % (bytearray.fromhex(mac_octets[0])[0] ^ 0x2)
        return f"fe80::{mac_octets[0]}{mac_octets[1]}:{mac_octets[2]}ff:fe{mac_octets[3]}:{mac_octets[4]}{mac_octets[5]}"



    def post(self, request, *args, **kwargs):
        print(request.data)
        
        if request.data['switch'] is not None:
            try:
                switch = Switch.objects.get(hostname=request.data['switch'])
            except:
                switch = None
        else:
            switch = None

        model_slug = slugify(f"{request.data['vendor']} {request.data['model']}")
        
        if request.data['port'] is not None:
            try:
                port= SwitchPort.objects.get(name=request.data['port'], switch=switch)
            except:
                port = None
        else:
            port = None
        #print(port)
        if port is not None:
            nicQueryset = NetworkInterface.objects.all()
            nicQueryset = nicQueryset.filter(mac=None, switch_port=port)
            #print(nicQueryset)
            if nicQueryset is not None and len(nicQueryset) > 0:
                system = System.objects.get(pk=nicQueryset[0].system.pk)
                # print(model_slug)
                # print(system)
                # print(system.systemmodel.slug)
                if hasattr(system.systemmodel, "slug"):
                    if system.systemmodel.slug != model_slug:
                        system=None
                    if system is not None:
                        nicObj = nicQueryset.first()
                        nicObj.mac = request.data['mac']

                        # generate a Link-Local Address
                        nicObj.ipv6ll = self.mac2LL(nicObj.mac)

                        # attempt to set a GUA if a subnet is set on the port.
                        subnet = None
                        print(f"Port: {port}")
                        if port.networks is not None:
                            print(f"Net: {port.networks}")
                            if ":" in port.networks.subnet:
                                print(f"Subnet: {port.networks.subnet}")
                                subnet = port.networks.subnet
                        if subnet is not None:
                            # assign a GUA based off the LL
                            nicObj.ipv6gua = nicObj.ipv6ll.replace("fe80::", subnet)

                            # if we are on an IPv6 subnet, assign the IP to the GUA
                            if nicObj.ipaddress is None or nicObj.ipaddress == '':
                                nicObj.ipaddress = nicObj.ipv6gua
                        
                        nicObj.save()
                        # send in a pxe update job
                        JobType = None
                        try:
                            JobType = JobModule.objects.get(slug='pxe-update')
                        except:
                            JobType = None
                        # print(JobType)
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
        # Save the node to a NADS System if the mac isn't assigned
        sysnic = NetworkInterface.objects.all()
        sysnic = sysnic.filter(mac=request.data['mac'])
        if sysnic.count() > 0:
            return Response(None, status=200)
        else: 
            nadssys = NADSSystem.objects.update_or_create(
                mac=request.data['mac'],
                switch=request.data['switch'],
                port=request.data['port'],
                vendor=request.data['vendor'],
                model=request.data['model']
                )
        print(sysnic)
   
        # TODO insert MAC ban code here if needed.
        return Response(None, status=200)
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
        "config_params": "-- #Inherit from System Group or Distribtion.",
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
    serializer_class = SystemSerializer
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
#            #ip="172.16.12.1"
            nicQueryset = NetworkInterface.objects.all()
            nicQueryset = nicQueryset.filter(ipaddress=ip)
            if nicQueryset.count() == 0:
                return Response(None, status=404)
            system = nicQueryset[0].system
            # print(system)
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

        self.serializer_class = SystemSerializer
        return super().post(request, *args, **kwargs)
    def get(self, request, format=None, **kwargs):
        # XXX: Fix this to work with the base class
        # get() function
        
        if 'powerstate' in request.query_params:
            # get the power state via IPMI
            if 'pk' in kwargs:
                systemObj = System.objects.get(pk=kwargs['pk'])
                bmcObj = SystemBMC.objects.filter(system=systemObj)
                if bmcObj.count() != 1:
                    return redirect(f"/static/images/power_unknown.svg")

                try:
                    bmcStatus = func_timeout(1, SystemPowerAPIView()._doPowerCmd, [bmcObj[0], "status"])
                except FunctionTimedOut:
                    print("IPMI Command Timed Out")
                    return redirect(f"/static/images/power_unknown.svg")

                # TODO: Serve the image file based on status
                if bmcStatus['chassis_status'] == "unknown":
                    bmcStatus = "unknown"
                else:
                    bmcStatus = "on" if bmcStatus['chassis_status'] else "off"
                return redirect(f"/static/images/power_{bmcStatus}.svg")

            else:
                return redirect(f"/static/images/power_unknown.svg")
        
        if 'pk' in kwargs:
            self.serializer_class = SystemSerializer

            # someone is looking for a specific item.
            return self.retrieve(self, request, format=None, pk=kwargs['pk'])
         
        # call the base class get()
        # this does do some initial filtering.
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

        # post-query filters and such.
        if 'detail' in request.query_params:
            self.serializer_class = SystemDetailSerializer

        if 'hostname' in request.query_params:
            # someone is looking for a specific item.
            print('Hostname query: ?hostname=' + request.query_params['hostname'])
            self.queryset = self.model.objects.all()
            self.queryset = self.queryset.filter(hostname__contains=request.query_params['hostname'])
            if self.queryset.count() == 0:
                return Response(None, status=404)
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
                return Response({'msg': "Unknown System", 'ip':ip}, status=404)
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
        
        if 'network' in self.request.query_params:
            network = self.request.query_params['network']
            net = Network.objects.filter(slug=network)[0]
        #   
            # get the Network ID
            # This should first query the switch for all ports on that network.
            # It should also query all network interfaces for hard coded networks.
            # Then reconcile ports <--> interfaces.  Switch port takes precidence, if set.
            innerQ = SwitchPort.objects.filter(networks=net)
            swportqueryset = NetworkInterface.objects.all().filter(switch_port__in=innerQ)
            nicqueryset = NetworkInterface.objects.all().filter(network=net)
            nics = list(nicqueryset)
            print(swportqueryset.count())
            if swportqueryset.count() > 0:
                for portnic in swportqueryset:
                    # find the nic in nics 
                    # nics [ {nicobj} ]
                    found=False
                    for nic in nics:
                        if nic.id == portnic.id:
                            nic.network = portnic.network
                            found=True
                    if not found:
                        nics.append(portnic)

            # now we remove nics if they are not the set at the switchport
            for nic in nics:
                found=False
                if nic.switch_port is not None:
                    for portnic in swportqueryset:
                        if nic.id == portnic.id:
                            found=True
                            break
                    if not found:
                        nics.remove(nic)
                
                    
                    
            # now we have a list of nics return that as json
            return Response(NetworkInterfaceSerializer(nics, many=True).data)
        
        #     return generics.ListAPIView.get(self, request, format=None)
        
        # return the super call for get.
        return super().get(request, format=None, **kwargs)
        


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
    serializer_class = SystemImageSerializer
    jobservers=JobServerAPISerializer(many=True)
    
    def get(self, request, format=None, **kwargs):

        result = super().get(request, format, **kwargs)
        if 'pk' in kwargs:
            self.serializer_class = SystemImageDetailsSerializer
        return result

    def patch(self, request, *args, **kwargs):
      print(f"Query params: {request.query_params}")
      if 'addjs' in request.query_params:
        # if 'addjs' is in the query string, we are appending a jobserver to the 
        # jobserver array.
        print("Updating, not removing, via internal merge.")
        # first let's get the image in question
        sysimage = None
        print(f"data: {request.data}")
        if 'pk' in kwargs:

          sysimage = self.model.objects.get(pk=kwargs['pk'])
        if sysimage == None:
          return Response(None, status=404)
        if 'needs_rebuild' in request.data:
            sysimage.needs_rebuild = request.data['needs_rebuild']
        # if the incoming 'jobservers' param is an array, let's merge it with 
        # the existing one.
        if 'jobservers' in request.data:
          
          jobservers = list(sysimage.jobservers.all().values_list('id', flat=True))  
          if type(request.data['jobservers']) == list:
            # merge without duplicates
            print("Merging Array.")
            jobservers = list(set(jobservers + request.data['jobservers']))
            # remove the jobservers from the kwargs.
            del request.data['jobservers']
          else:
            print("Adding Jobserver")
            jobservers.append(request.data['jobservers'])
            # jobservers isn't a list, let's try to append our new jobserver.
          sysimage.jobservers.set(jobservers)
          sysimage.save()
        
      return super().patch(request, *args, **kwargs)
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
    serializer_class = SystemBMCSerializer
    queryset = None
    def get(self, request, format=None, **kwargs):
        if 'pk' in kwargs:
            self.serializer_class = SystemBMCDetailSerializer
        if 'detail' in request.query_params:
            self.serializer_class = SystemBMCDetailSerializer
        return super().get(request, format, **kwargs)

    def post(self, request, *args, **kwargs):
        print(request.data)
        if request.data['password'] == "":
            del request.data['password']
        return super().post(request, *args, **kwargs)

    
    def patch(self, request, *args, **kwargs):
        print(request.data)
        if 'password' in request.data and request.data['password'] == "":
            del request.data['password']
        return super().patch(request, *args, **kwargs)   

class SystemPowerAPIView(MProvView):
    model = SystemBMC
    serializer_class = SystemBMCSerializer
    queryset = None
    def get(self, request, format=None, **kwargs):
        if 'action' not in kwargs:
            # return 400 Bad Request
            return Response("Bad Request", status=400)
        # Attempt to get the bmc(s) in question.
        # check our query and see if we can get filters based on the query
        if 'hostname' in request.query_params:
            # someone is searching by hostname
            system_results= System.objects.filter(hostname__contains=request.query_params['hostname'])
            if system_results.count() > 0:
                if system_results.count() > 10: 
                    print("WARN: Large node set returned, truncating.")
                    system_results = system_results[:10]
                self.queryset=self.model.objects.filter(system__in=system_results)
                results = {}
                for bmc in self.queryset:
                    results[str(bmc)] = self._doPowerCmd(bmc, kwargs['action'])
                
                return Response(results, status=200) 
            else :
                return Response(None, status=404)
        if 'id' in request.query_params:
            system_results= System.objects.get(id=request.query_params['id'])
            if system_results is None:
                return Response(None, status=404)
            self.queryset = self.model.objects.filter(system=system_results.id)
            results = {}
            for bmc in self.queryset:
                results[str(bmc)] = self._doPowerCmd(bmc, kwargs['action'])
            return Response(results, status=200)

        error_body = {}
        for field in request.query_params:
            #print(field)
            if field == 'detail':
                # ignore the detail flag.
                continue
            if any(x for x in self.model._meta.get_fields() if x.name == field):
                # we found a field.
                try:
                    self.queryset = self.queryset.filter((field,request.query_params[field]))
                except BaseException as e:
                    error_body[field] = f"Error searching for {field}: {type(e)=}: {e=}"
            else: 
                error_body[field] = f"Error searching for {field}: Field doesn't exist."
        if len(error_body) > 0:
            return Response(error_body, status=400)
        if self.queryset.count() == 0:
            return Response(None, status=404)


    def _doPowerCmd(self, bmc, action="on"):
        print(f"Bmc: {bmc.ipaddress}, user: {bmc.username}, pass: {bmc.password}, action: {action}")
        interface = pyipmi.interfaces.create_interface('rmcp', slave_address=0x81,
                                               host_target_address=0x20,
                                               keep_alive_interval=0)
        interface = pyipmi.interfaces.create_interface('ipmitool', interface_type='lanplus')
        #interface.set_timeout(2)
        ipmi = pyipmi.create_connection(interface)
        ipmi.session.set_session_type_rmcp(bmc.ipaddress, 623)
        ipmi.session.set_auth_type_user(bmc.username, bmc.password)
        
        
        if action == "pxe" or  action == "pxeefi":
            efiopt=""
            if action == "pxeefi":
                efiopt = "options=efiboot"
        
            # XXX: bootdev is not implemented in python-ipmi(pyipmi)
            # so we will need to issue a raw ipmitool command.
            ipmitool_cmd = f"/usr/bin/ipmitool -Ilanplus -U{bmc.username} -P{bmc.password} -H{bmc.ipaddress} chassis bootdev pxe {efiopt}"
            print(ipmitool_cmd)
            try:
                subprocess.run(args=ipmitool_cmd.split())
            except: 
                print("Error Setting PXE.")
                return
            # force a reset
            action = "reset"
            # make sure we are powered on
            try:
                ipmi.session.establish()
                ipmi.target = pyipmi.Target(ipmb_address=0x20)
                ipmi.chassis_control_power_up()
            except:
                print("Host Already Up")
        try:
            ipmi.session.establish()
            ipmi.target = pyipmi.Target(ipmb_address=0x20)    
            print(f"IPMI Power Action {action}")     
            if action=="on":
                print("Issue power up... ")
                ipmi.chassis_control_power_up()
            elif action=="off":
                print("Issue power off... ")
                ipmi.chassis_control_power_down()
            elif action=="reset":
                try:
                    print("Issue hard_reset ... ")
                    ipmi.chassis_control_hard_reset()
                except:
                    print("Issue power cycle ... ")
                
                ipmi.chassis_control_power_cycle()
                
            elif action=="cycle":
                print("Issue power cycle ... ")
                ipmi.chassis_control_power_cycle()
            elif action=="status": 
                
                chassis = ipmi.get_chassis_status()
             
                return({'details': '', 'status': 200, 'chassis_status': chassis.power_on})
        except Exception as e:
            return({'details': f"Exception {e}", "status": "400", 'chassis_status': 'unknown'})

    def post(self, request, *args, **kwargs):
        return Response("Bad Request", status=400)
    def patch(self, request, *args, **kwargs):
        return Response("Bad Request", status=400)
    def delete(self, request, *args, **kwargs):
        return Response("Bad Request", status=400)
    def put(self, request, *args, **kwargs):
        return Response("Bad Request", status=400)
