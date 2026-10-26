import os
import subprocess
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from .serializers import (
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
from networks.models import SwitchPort, Network, Switch
from rest_framework import generics
from jobqueue.models import Job, JobModule, JobStatus
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
- This will register the MAC in the packet to the system that has a NIC
with no MAC on the specified switch and port, if that system's model matches
the vendor and model in the packet.  The NIC also gets an IPv6 link-local
address (and a GUA if the port's network is IPv6), a pxe-update job is queued,
and the system is returned as a JSON list.
- If no system matches and the MAC is not already assigned to a NIC, the packet
is saved as a N.A.D.S. discovered system.  Returns 200 with an empty body.
- All fields except "serial" are required ("switch" and "port" may be null).
A missing field returns 400 with an error for each one.

NADS Packet:


        {
            "vendor": The vendor associated with the system you wish to register, must match what mPCC knows.
            "model": The model associated with the system you wish to register, must match what mPCC knows.
            "switch": "some-switch-host-name", must match what mPCC knows.
            "port": "some-port-name", must match what mPCC knows.
            "mac": MAC of the machine being registered
            "serial": the serial number from dmidecode (currently ignored)
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
        if mac is None:
            return None
        mac_octets = mac.split(":")
        # take the first octet and invert the 2nd to last bit.
        mac_octets[0] = "%X" % (bytearray.fromhex(mac_octets[0])[0] ^ 0x2)
        return f"fe80::{mac_octets[0]}{mac_octets[1]}:{mac_octets[2]}ff:fe{mac_octets[3]}:{mac_octets[4]}{mac_octets[5]}"



    def post(self, request, *args, **kwargs):
        missing = [field for field in ('vendor', 'model', 'switch', 'port', 'mac') if field not in request.data]
        if missing:
            return Response({field: "This field is required." for field in missing}, status=400)

        if request.data['switch'] is not None:
            try:
                switch = Switch.objects.get(hostname=request.data['switch'])
            except (Switch.DoesNotExist, Switch.MultipleObjectsReturned):
                switch = None
        else:
            switch = None

        model_slug = slugify(f"{request.data['vendor']} {request.data['model']}")
        
        if request.data['port'] is not None:
            try:
                port= SwitchPort.objects.get(name=request.data['port'], switch=switch)
            except (SwitchPort.DoesNotExist, SwitchPort.MultipleObjectsReturned):
                port = None
        else:
            port = None
        if port is not None:
            nicQueryset = NetworkInterface.objects.all()
            nicQueryset = nicQueryset.filter(mac=None, switch_port=port)
            if nicQueryset is not None and len(nicQueryset) > 0:
                system = System.objects.get(pk=nicQueryset[0].system.pk)
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
                        if port.networks is not None:
                            if ":" in port.networks.subnet:
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
                        except JobModule.DoesNotExist:
                            JobType = None
                        # look up the job module in the DB
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
            # mac is unique, so it's the only lookup field; a known MAC seen on
            # a new switch or port updates the existing entry.
            NADSSystem.objects.update_or_create(
                mac=request.data['mac'],
                defaults={
                    'switch': request.data['switch'],
                    'port': request.data['port'],
                    'vendor': request.data['vendor'],
                    'model': request.data['model'],
                    # XXX Future: 'serial': request.data['serial']
                })
   
        # TODO insert MAC ban code here if needed.
        return Response(None, status=200)
        # pass
        # return  generics.ListAPIView.get(self, request, format=None)

class SystemAPIView(MProvView):
    '''
# /systems/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, e.g. /systems/1/)
- POST (no primary key, e.g. /systems/)
- PATCH (with primary key, e.g. /systems/1/)
- DELETE (with primary key, e.g. /systems/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- hostname: The hostname of the server
- timestamp: The creation time of the entry
- created_by: The user who created this entry
- updated: Timestamp of the last update
- systemgroups: array of system group IDs
- config_params: The configuration parameters for this entry
- systemimage: The ID of the system image.
- systemmodel: The ID of the system model.
- location: The ID of the system location.
- stateful: Should this system install its image to disk?
- disks: array of disk layout IDs
- scripts: array of script IDs
- ansibleplaybooks, ansibleroles, ansiblecollections: arrays of Ansible IDs
- install_kernel_cmdline, tmpfs_root_size, initial_mods, prov_interface: boot options for this system
- config: The merged configuration from the OS Distro, System Groups, and this system

### Query Parameters
- ?FIELD=VALUE: GET (no primary key) only returns entries where that field matches exactly.
- ?hostname=TEXT: GET only returns systems whose hostname contains the text, or 404 if none.
    It can be combined with ?FIELD=VALUE filters.
- ?detail: GET (no primary key) returns systems with nested details.
- ?self: GET returns the system that owns the NIC with the requesting IP address, with
    nested details, or 404 if unknown.  POST with ?self and a body of {"netboot": false}
    clears the requesting system's provision flag, so it boots locally; {"netboot": true}
    sets it and makes the requesting NIC the system's bootable NIC.  Any other key returns
    403 and a non-boolean value 400, without changing anything.
- ?powerstate: GET with a primary key redirects to a power_on, power_off, or power_unknown
    status image.

### GET method (no parameters)
Returns a JSON list of all objects in the mPCC of this type

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
        "config_params": "-- #Inherit from System Group or Distribution.",
        "created_by": 1,
        "systemimage": "compute",
        "systemgroups": [
        2
        ],
        "scripts": []
    }
    ]



### GET, PATCH, DELETE (with primary key) and POST (no primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST Creates a new entry and is sent to the
    collection URL without a primary key.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if unchanged.

- GET returns the object specified (IDs only, no nested objects) or 404

- POST returns the new object created or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = System
    serializer_class = SystemSerializer
    queryset = None

    def post(self, request, *args, **kwargs):
        if 'self' in request.query_params:
            # someone would like to modify themselves.
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
                return Response({"detail": f"No network interface has the IP address {ip}."}, status=404)
            nic = nicQueryset[0]
            system = nic.system
            for arg in request.data:
                if arg != "netboot":
                    # Unsupported, return 403 forbidden
                    return Response(None, status=403)
            netboot = request.data.get("netboot")
            if isinstance(netboot, str) and netboot.lower() in ("true", "false"):
                netboot = netboot.lower() == "true"
            if not isinstance(netboot, bool):
                return Response({"netboot": "Must be true or false."}, status=400)
            if netboot:
                # boot from the NIC that asked; saving it clears bootable on the others.
                nic.bootable = True
                nic.save()
            system.provision = netboot
            system.save()
            return Response({"provision": system.provision, "bootable_nic": nic.name}, status=200)

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
                    return redirect("/static/images/power_unknown.svg")

                try:
                    bmcStatus = func_timeout(1, SystemPowerAPIView()._doPowerCmd, [bmcObj[0], "status"])
                except FunctionTimedOut:
                    print("IPMI Command Timed Out")
                    return redirect("/static/images/power_unknown.svg")

                # TODO: Serve the image file based on status
                if bmcStatus['chassis_status'] == "unknown":
                    bmcStatus = "unknown"
                else:
                    bmcStatus = "on" if bmcStatus['chassis_status'] else "off"
                return redirect(f"/static/images/power_{bmcStatus}.svg")

            else:
                return redirect("/static/images/power_unknown.svg")
        
        if 'pk' in kwargs:
            self.serializer_class = SystemSerializer

            # someone is looking for a specific item.
            return self.retrieve(request, pk=kwargs['pk'])
         
        result = self.checkContentType(request, format=format)
        if result is not None:
            return result

        # ?FIELD=VALUE filters from the base class. hostname is a contains
        # match instead, below.
        self.queryset, error_body = self.filter_by_query_params(request, kwargs, skip=('hostname',))
        if len(error_body) > 0:
            return Response(error_body, status=400)

        # post-query filters and such.
        if 'detail' in request.query_params:
            self.serializer_class = SystemDetailSerializer

        if 'hostname' in request.query_params:
            # someone is looking for a specific item.
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
- GET (with Primary Key, e.g. /systemgroups/1/)
- POST (no primary key, e.g. /systemgroups/)
- PATCH (with primary key, e.g. /systemgroups/1/)
- DELETE (with primary key, e.g. /systemgroups/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: The name of the system group
- config_params: The configuration parameters for this entry
- scripts: A list of scripts that will run on this group
- ansibleplaybooks, ansibleroles, ansiblecollections: Ansible content for this group
    (all four are returned as nested objects, and sent as arrays of IDs on POST and PATCH)
- install_kernel_cmdline, tmpfs_root_size, initial_mods, prov_interface: boot options for this group
- systems: array of system IDs in this group

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.
- ?FIELD=VALUE: GET (no primary key) only returns entries where that field matches exactly.

### GET method (no parameters)
Returns a JSON list of all objects in the mPCC of this type.  Scripts and Ansible
content are returned as nested objects; the example below is abbreviated.

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


### GET, PATCH, DELETE (with primary key) and POST (no primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST Creates a new entry and is sent to the
    collection URL without a primary key.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if unchanged.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = SystemGroup
    serializer_class = SystemGroupSerializer

class NetworkInterfaceAPIView(MProvView):
    '''
# /networkinterfaces/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, e.g. /networkinterfaces/1/)
- POST (no primary key, e.g. /networkinterfaces/)
- PATCH (with primary key, e.g. /networkinterfaces/1/)
- DELETE (with primary key, e.g. /networkinterfaces/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- name: The name of the interface
- hostname: The hostname for this interface to be registered to DNS/DHCP (set to the system's hostname on save)
- hostaliases: A space-separated list of alternate hostnames
- ipaddress: The IP address to be registered to DNS/DHCP for this interface
- ipv6ll: The IPv6 link-local address
- ipv6gua: The IPv6 SLAAC global unicast address
- mac: The MAC address of this interface
- mtu: The MTU of this interface
- isgateway: Is this the gateway NIC?
- bootable: Does the system PXE boot from this NIC?  A system has at most one bootable
    NIC; saving one as bootable clears it on the others.
- system: The system ID this NIC is associated with
- switch_port: The switch port ID this NIC is connected to.
- network: The network ID this NIC is on.

### Query Parameters
- ?network=SLUG: GET returns the NICs on that network, either set directly on the NIC or
    through the network of the NIC's switch port, or 404 if there is no such network.
    The switch port's network takes precedence: those NICs are listed with this network,
    and a NIC whose switch port is on another network is left out.
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.
    Not with ?network, which always returns plain IDs.
- ?FIELD=VALUE: GET (no primary key) only returns entries where that field matches exactly.

### GET method (no parameters)
Returns a JSON list of all objects in the mPCC of this type

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


### GET, PATCH, DELETE (with primary key) and POST (no primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST Creates a new entry and is sent to the
    collection URL without a primary key.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if unchanged.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = NetworkInterface
    serializer_class = NetworkInterfaceSerializer
    def get(self, request, format=None, **kwargs):
        
        if 'network' in self.request.query_params:
            network = self.request.query_params['network']
            net = Network.objects.filter(slug=network).first()
            if net is None:
                return Response(None, status=404)
            # Return the NICs on a switch port on this network, and the NICs
            # set to this network directly.  Switch port takes precedence: a
            # NIC whose port is on this network is listed with this network,
            # and a NIC whose port is on another network is left out.
            portnics = {nic.id: nic for nic in NetworkInterface.objects.filter(switch_port__networks=net)}
            nics = []
            for nic in NetworkInterface.objects.filter(network=net):
                if nic.id in portnics:
                    nics.append(portnics.pop(nic.id))
                elif nic.switch_port is None:
                    nics.append(nic)
            nics.extend(portnics.values())
            for nic in nics:
                nic.network = net

            # now we have a list of nics return that as json
            return Response(NetworkInterfaceSerializer(nics, many=True).data)
        
        #     return generics.ListAPIView.get(self, request, format=None)
        
        # return the super call for get.
        return super().get(request, format=None, **kwargs)
        


class SystemImagesAPIView(MProvView):
    
    '''
# /systemimages/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, e.g. /systemimages/compute/)
- POST (no primary key, e.g. /systemimages/)
- PATCH (with primary key, e.g. /systemimages/compute/)
- DELETE (with primary key, e.g. /systemimages/compute/)

/systemimages/PK/details and /systemimages/PK/update behave the same as /systemimages/PK/.

## Documentation

### Class Attributes
- slug: a machine parsable version of the name
- name: A human readable name
- timestamp: (Optional) The time this entry was created
- created_by: The User that is creating this 
- updated: (Auto) The time this entry was last updated
- systemgroups: Array of system groups this system image is a part of (returned as
    nested objects, sent as an array of IDs on POST and PATCH)
- needs_rebuild: If the user is asking to rebuild this image.
- version: used internally for tracking when an image changes
- jobservers: array of jobservers actively serving this version of this image.
- config_params: YAML of config parameters set on this system image, used by scripts
- osdistro: the distro to base this image off of.
- osrepos: (Optional) extra repos for this image.
- scripts: array of script IDs for this image
- ansibleplaybooks, ansibleroles, ansiblecollections: arrays of Ansible IDs
- customIPXE: (Optional) a custom iPXE script served instead of the generated one

### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.
- ?FIELD=VALUE: GET (no primary key) only returns entries where that field matches exactly.
- ?addjs: PATCH merges the passed jobservers (a list or a single ID) into the
    existing jobservers instead of replacing them.

### GET method (no parameters)
Returns a JSON list of all objects in the mPCC of this type.  System groups are
returned as nested objects; the example below is abbreviated.

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
        "config_params": "- rootpw: '$6$<salt>$<hash>'",
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

### GET, PATCH, DELETE (with primary key) and POST (no primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST Creates a new entry and is sent to the
    collection URL without a primary key.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if unchanged.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.


    '''
    model = SystemImage
    queryset = SystemImage.objects.all()
    serializer_class = SystemImageSerializer
    detail_serializer_class = SystemImageDetailsSerializer

    def patch(self, request, *args, **kwargs):
      if 'addjs' in request.query_params:
        # if 'addjs' is in the query string, we are appending a jobserver to the 
        # jobserver array.
        # first let's get the image in question
        sysimage = None
        if 'pk' in kwargs:

          sysimage = self.model.objects.get(pk=kwargs['pk'])
        if sysimage is None:
          return Response(None, status=404)
        if 'needs_rebuild' in request.data:
            sysimage.needs_rebuild = request.data['needs_rebuild']
        # if the incoming 'jobservers' param is an array, let's merge it with 
        # the existing one.
        if 'jobservers' in request.data:
          
          jobservers = list(sysimage.jobservers.all().values_list('id', flat=True))  
          if type(request.data['jobservers']) is list:
            # merge without duplicates
            jobservers = list(set(jobservers + request.data['jobservers']))
          else:
            jobservers.append(request.data['jobservers'])
            # jobservers isn't a list, let's try to append our new jobserver.
          # remove the jobservers from the request data, so the update below
          # doesn't replace the merged list.
          del request.data['jobservers']
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
- GET (with Primary Key, e.g. /systembmcs/1/)
- POST (no primary key, e.g. /systembmcs/)
- PATCH (with primary key, e.g. /systembmcs/1/)
- DELETE (with primary key, e.g. /systembmcs/1/)

## Documentation

### Class Attributes
- id: The internal ID in the db
- ipaddress: The IP of the entry
- mac: The MAC address of the entry
- username: The username for authentication with this entry
- password: The password for authentication with this entry. It is write-only:
    GET returns it only for a single entry (/systembmcs/1/) or with `?detail`.
    An empty password on POST or PATCH is ignored.
- system: ID of the system this entry is associated with.
- switch_port: ID of the switchport this entry resides on.
- network: ID of the network this entry is on.
- ipv6ll: The IPv6 link-local address of the entry
- vlan: The VLAN ID of the entry

### Query Parameters
- ?detail: GET (no primary key) returns entries with their system, switch port and network nested
    one level, and the password.
- ?FIELD=VALUE: GET (no primary key) only returns entries where that field matches exactly.

### GET method (no parameters)
Returns a JSON list of all objects in the mPCC of this type

Format returned:


    [
    {
        "id": 1,
        "ipaddress": "172.16.20.1",
        "mac": null,
        "username": null,
        "system": 1,
        "switch_port": null
    }
    ]


### GET, PATCH, DELETE (with primary key) and POST (no primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST Creates a new entry and is sent to the
    collection URL without a primary key.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if unchanged.

- GET returns the object specified, with its system, switch port and network
    nested one level, or 404

- POST returns the new object created or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = SystemBMC
    serializer_class = SystemBMCSerializer
    detail_serializer_class = SystemBMCDetailSerializer
    queryset = None

    def post(self, request, *args, **kwargs):
        if request.data.get('password') == "":
            del request.data['password']
        return super().post(request, *args, **kwargs)

    
    def patch(self, request, *args, **kwargs):
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
            system_results= System.objects.filter(hostname=request.query_params['hostname'])
            if system_results.count() > 0:
                if system_results.count() > 10: 
                    print("WARN: Large node set returned, truncating.")
                    system_results = system_results[:10]
                self.queryset=self.model.objects.filter(system__in=system_results)
                results = {}
                for bmc in self.queryset:
                    results[str(bmc)] = self._powerAction(bmc, kwargs['action'])
                
                return Response(results, status=200) 
            else :
                return Response(None, status=404)
        if 'id' in request.query_params:
            try:
                system_results= System.objects.filter(id=request.query_params['id']).first()
            except ValueError:
                return Response({'id': "Must be a system ID."}, status=400)
            if system_results is None:
                return Response(None, status=404)
            if kwargs['action'] in self.PXE_ACTIONS and not system_results.enable_provisioning():
                return Response(self._noBootableNIC(system_results), status=409)
            self.queryset = self.model.objects.filter(system=system_results.id)
            results = {}
            for bmc in self.queryset:
                results[str(bmc)] = self._doPowerCmd(bmc, kwargs['action'])
            return Response(results, status=200)

        # otherwise act on the BMCs matching ?FIELD=VALUE filters on the BMC
        # fields, up to 10 of them, like ?hostname=.
        error_body = {}
        filtered = False
        for field in request.query_params:
            if field == 'detail':
                # ignore the detail flag.
                continue
            if any(x for x in self.model._meta.get_fields() if x.name == field):
                # we found a field.
                try:
                    self.queryset = self.queryset.filter((field,request.query_params[field]))
                    filtered = True
                except BaseException as e:
                    error_body[field] = f"Error searching for {field}: {type(e)=}: {e=}"
            else: 
                error_body[field] = f"Error searching for {field}: Field doesn't exist."
        if len(error_body) > 0:
            return Response(error_body, status=400)
        if not filtered:
            # never act on every BMC at once.
            return Response("Bad Request: pass ?hostname=, ?id= or a BMC field filter.", status=400)
        if self.queryset.count() == 0:
            return Response(None, status=404)
        if self.queryset.count() > 10:
            print("WARN: Large BMC set returned, truncating.")
        results = {}
        for bmc in self.queryset[:10]:
            results[str(bmc)] = self._powerAction(bmc, kwargs['action'])
        return Response(results, status=200)

    PXE_ACTIONS = ("pxe", "pxeefi")

    def _noBootableNIC(self, system):
        return {'details': f"{system} has no bootable network interface, so it can't PXE boot.  It was not reset.", 'status': 409, 'chassis_status': 'unknown'}

    def _powerAction(self, bmc, action):
        # a PXE boot provisions the system, which needs a bootable NIC to boot from.
        if action in self.PXE_ACTIONS and not bmc.system.enable_provisioning():
            return self._noBootableNIC(bmc.system)
        return self._doPowerCmd(bmc, action)

    def _doPowerCmd(self, bmc, action="on"):
        print(f"Bmc: {bmc.ipaddress}, user: {bmc.username}, action: {action}")
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
            # -E reads the password from IPMI_PASSWORD, keeping it out of the process list.
            ipmitool_cmd = ["/usr/bin/ipmitool", "-Ilanplus", f"-U{bmc.username}", "-E", f"-H{bmc.ipaddress}", "chassis", "bootdev", "pxe"] + efiopt.split()
            ipmitool_env = {**os.environ, "IPMI_PASSWORD": bmc.password or ""}
            try:
                subprocess.run(args=ipmitool_cmd, env=ipmitool_env)
            except OSError:
                print("Error Setting PXE.")
                return
            # force a reset
            action = "reset"
            # make sure we are powered on
            try:
                ipmi.session.establish()
                ipmi.target = pyipmi.Target(ipmb_address=0x20)
                ipmi.chassis_control_power_up()
            except Exception as e:
                print(f"Power-on before reset failed (host may already be on): {e}")
        try:
            ipmi.session.establish()
            ipmi.target = pyipmi.Target(ipmb_address=0x20)    
            print(f"IPMI Power Action: {action}")     
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
                except Exception:
                    # Only fall back to a power cycle if the hard reset failed.
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
