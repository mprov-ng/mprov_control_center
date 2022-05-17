from http.client import NETWORK_AUTHENTICATION_REQUIRED
import ipaddress
from re import template
from unicodedata import name
from .serializers import (
    NetworkInterfaceDetailsSerializer,
    NetworkInterfaceSerializer,
    SystemSerializer,
)
from rest_framework.response import Response

from common.views import MProvView
from systems.models import NetworkInterface, System, SystemGroup, SystemImage
from django.shortcuts import render
from rest_framework.response import Response
from django.db.models import Prefetch
from networks.models import SwitchPort, Network, Switch
from rest_framework import status, generics
from django.template import Template, Context
from jobqueue.models import Job, JobModule, JobStatus



class SystemRegAPIView(MProvView):
    model = System
    serializer_class = SystemSerializer
    queryset = System.objects.none()
    def post(self, request, *args, **kwargs):
        print(request.data)
        
        switch = Switch.objects.get(hostname=request.data['switch'])
        print(switch)
        
        port= SwitchPort.objects.get(name=request.data['port'], switch=switch)
        print(port)
        nicQueryset = NetworkInterface.objects.all()
        nicQueryset = nicQueryset.filter(mac=None, switch_port=port)
        print(nicQueryset)
        if nicQueryset is not None and len(nicQueryset) > 0:
            system = System.objects.get(pk=nicQueryset[0].system.pk)
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
                return Response(self.get_serializer_class.serialize('json', [system]))
        return  generics.ListAPIView.get(self, request, format=None)

class SystemAPIView(MProvView):
    model = System
    template = "systems_docs.html"
    serializer_class = SystemSerializer
    queryset = None
    def get(self, request, format=None, **kwargs):
        result = self.checkContentType(request, format=format, kwargs=kwargs)
        if result is not None:
            return result
        if self.model == None:
            return Response(None)
        self.queryset = self.model.objects.all()
        if 'hostname' in request.query_params:
            # someone is looking for a specific item.
            queryset = self.queryset.filter(hostname=request.query_params['hostname'])
            if queryset.count() == 0:
                return Response(None, status=404)
            return generics.ListAPIView.get(self, request, format=None)
        return Response(None, status=500)


class SystemGroupAPIView(MProvView):
      model = SystemGroup
      template = "systemgroup_docs.html"

class NetworkInterfaceAPIView(MProvView):
      model = NetworkInterface
      template = "networkinterface_docs.html"
      serializer_class = NetworkInterfaceSerializer
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
            # get the Network ID
            net = Network.objects.filter(slug=network)
            innerQ = SwitchPort.objects.filter(networks__in=net)
            queryset = self.model.objects.filter(switch_port__in=innerQ)
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None)


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
        # result = self.checkContentType(request, format=format, kwargs=kwargs)
        # if result is not None:
        #     return result
        # grab the IP
        ip=""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        # ip="172.16.30.1"
        # print(ip)
        # now try to grab the nic for this IP
        queryset = self.model.objects.all()
        queryset = queryset.filter(ipaddress=ip)

        # our IP is not found, let's see if NADS is running on here.
        if queryset.count() == 0:
            imgQs = SystemImage.objects.get(name='__nads__')
            
            if type(imgQs) is SystemImage:  
                # there is a __nads__ iamge, let's serve that.
                # spoof a nics object
                class Obj: pass
                system=Obj()
                system.systemimage = imgQs
                # setattr(system, 'systemima?ge', imgQs)
                nic = Obj()
                nic.system = system
                # setattr(nic, 'system', system)

                nics = [ nic ]
                queryset = nics

        # print(queryset)
        # the following lines allow recurive templating to be done on the kernel cmdline.
        for nic in queryset:
            template = Template(nic.system.systemimage.osdistro.install_kernel_cmdline)
            # print(nic)
            context = Context(dict(nic=nic))
            rendered: str = template.render(context)
            nic.system.systemimage.osdistro.install_kernel_cmdline = rendered


        context= {
            'nics': queryset,
        }
        print("PXE Request from: " + ip)
        # print(context['nics'])
        return(render(template_name="ipxe", request=request, context=context, content_type="text/plain" ))
        pass

