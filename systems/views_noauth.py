
import os
from urllib import response
from .models import SystemImage, NetworkInterface
from django.shortcuts import redirect
from rest_framework.exceptions import NotFound
import random
from common.views import MProvView
from systems.serializers import SystemImageSerializer, NetworkInterfaceDetailsSerializer
from rest_framework import generics
from django.http import HttpResponseNotAllowed
from rest_framework.response import Response
from django.template import Template, Context
from django.shortcuts import render
import requests


class ImagesAPIView(MProvView, generics.ListAPIView):
    '''
# /images/

NOTE: This is a special API Access point for retrieving system images, initramfs, and such
This API ONLY expects keys to images.  If they primary key does not exist, a 404 is returned.
If no primary key is specified, 404 is returned.

## Accepted HTTP Methods:
- GET (with Primary Key, ie: /images/compute/)


## Documentation

### GET (with primary key)
- Will return the binary of the image requested, regardless of requested content type.

    '''
    model = SystemImage
    authentication_classes = [] #disables authentication
    permission_classes = [] #disables permission
    serializer_class = SystemImageSerializer
    def get(self, request, format=None, *args, **kwargs):

      isInitRamFS=False
      if 'pk' in kwargs:
        req = kwargs['pk'].split('.', 1)
        imgName = req[0]
        if len(req) > 1:
          # getting an extension
          if(req[1] == "initramfs"):
            # this is an initramfs query.
            isInitRamFS=True

        image = SystemImage.objects.get(pk=imgName)
      else: 
        # no pk in image, spit out a list then.
        result = self.checkContentType(request, format=format, kwargs=kwargs)
        if result is not None:
            return result  
        # no pk in image, spit out a list then.
        self.queryset = SystemImage.objects.all()
        print(self.queryset)
        return(generics.ListAPIView.get(self, request, format=None)) 
      # choose a jobserver with the lowest one minute load avg.
      js_set = self.getJobserver(image)
      js = None
      js = js_set[0]
      imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug
      if isInitRamFS:
        imageURL += ".initramfs"
      else:
        imageURL += ".img"  
      try: 
        response = requests.head(imageURL,timeout=1)
        statCode = response.status_code
      except:
        statCode = 0
      while ( statCode <= 199 or statCode >=400):
        # jobsever gave a bad response, remove it and retry.
        js_set.remove(js)
        print("Removing Jobserver " + str(js) + ", URL: " + imageURL + " not accessible. Status: " + str(statCode))
        image.jobservers.set(js_set)
        image.save()
        js_set = self.getJobserver(image)
        js = None
        js = js_set[0]
        imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug
        if isInitRamFS:
          imageURL += ".initramfs"
        else:
          imageURL += ".img"  
        try: 
          response = requests.head(imageURL,timeout=1)
          statCode = response.status_code
        except: 
          statCode=0
      return redirect(imageURL)        

    def getJobserver(self, image):
      # choose a jobserver with the lowest one minute load avg.
      js_set = list(image.jobservers.all().order_by('one_minute_load'))
        
      if(len(js_set)==0):
        # if there are no jobservers, return 404
        raise NotFound(detail="Error 404, No Jobservers for Image", code=404)
      print("Jobserver: " + str(js_set[0]))
      return js_set

    def post(self, request, *args, **kwargs):
      return HttpResponseNotAllowed(["GET"])

    def delete(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

    def put(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

    def patch(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

class KernelImageAPIView(MProvView, generics.ListAPIView):
      '''
# /kernels/
NOTE: This is a mimic of the /images/ function but specifically for serving 
kernels to PXE.  This function may be merged into /images/ at some point.


## Accepted HTTP Methods:
- GET (with Primary Key, ie: /kernels/compute/)

## Documentation

### Class Attributes


### GET (with primary key)
- Will return the kernel requested, regardless of requested content type.

    '''
      model = SystemImage
      # TODO: placeholder for now to test 302 redirects
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      serializer_class = SystemImageSerializer
      def get(self, request, format=None, *args, **kwargs):
        # result = self.checkContentType(request, format=format, kwargs=kwargs)
        # if result is not None:
        #     return result
        if 'pk' in kwargs:
          image, _= os.path.splitext(kwargs['pk'])
          image = SystemImage.objects.get(pk=image)
        else: 
          result = self.checkContentType(request, format=format, kwargs=kwargs)
          if result is not None:
              return result 
          # no pk in image, spit out a list then.
          self.queryset = SystemImage.objects.all()
          return(generics.ListAPIView.get(self, request, format=None))
        # choose a jobserver with the lowest one minute load avg.
        js_set = self.getJobservers(image)
        js = js_set[0]
        imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug + ".vmlinuz"
        
        try: 
          response = requests.head(imageURL,timeout=1)
          statCode = response.status_code
        except:
          statCode = 0
        while ( statCode <= 199 or statCode >=400):
          # jobsever gave a bad response, remove it and retry.
          js_set.remove(js)
          print("Removing Jobserver " + str(js) + ", URL: " + imageURL + " not accessible. Status: " + str(statCode))
          image.jobservers.set(js_set)
          image.save()
          js_set = self.getJobservers(image)
          js = js_set[0]
          imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug + ".vmlinuz"
          print(imageURL)
          try: 
            response = requests.head(imageURL,timeout=5)
            statCode = response.status_code
          except: 
            statCode=0
        return redirect(imageURL)        
      def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

      def delete(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def put(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def patch(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def getJobservers(self, image):
        # choose a jobserver with the lowest one minute load avg.
        js_set = list(image.jobservers.all().order_by('one_minute_load'))
        print("Jobserver: " + str(js_set[0]))
        if(len(js_set)==0):
          # if there are no jobservers, return 404
          raise NotFound(detail="Error 404, No Jobservers for Image", code=404)
        print("Jobserver: " + str(js_set[0]))
        return js_set

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
            try:
                imgQs = SystemImage.objects.get(name='__nads__')
            except:
                print(f"Error: You are missing a system image of the name '__nads__' so autodetection will fail.")
                return Response(None, status=404)
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
