
from .models import SystemImage
from rest_framework.views import APIView
from django.shortcuts import redirect
from rest_framework import mixins
from rest_framework.exceptions import NotFound
import random
from rest_framework.generics import GenericAPIView
from common.views import MProvView
from systems.serializers import SystemImageSerializer, SystemImageUpdateSerializer
from osmanagement.models import OSDistro, OSRepo
from rest_framework.response import Response
from jobqueue.models import JobServer
from rest_framework import generics


class SystemImageAPIView(generics.ListAPIView):
      model = SystemImage
      # TODO: placeholder for now to test 302 redirects
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
          self.queryset = SystemImage.objects.all()
          return(generics.ListAPIView.get(self, request, format=None))
        # choose a random jobserver
        js_set = list(image.jobservers.all())
        js = None
        if(len(js_set)==0):
          # if there are no jobservers, return 404
          raise NotFound(detail="Error 404, No Jobservers for Image", code=404) 
        print(js_set)
        js = random.choice(js_set)
        imageURL = "http://" + js.address + "/" + image.slug
        if isInitRamFS:
          imageURL += ".initramfs"
        else:
          imageURL += ".img"

        return redirect(imageURL)
class KernelImageAPIView(generics.ListAPIView):
      model = SystemImage
      # TODO: placeholder for now to test 302 redirects
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      serializer_class = SystemImageSerializer
      def get(self, request, format=None, *args, **kwargs):
        if 'pk' in kwargs:
          image = SystemImage.objects.get(pk=kwargs['pk'])
        else: 
          # no pk in image, spit out a list then.
          self.queryset = SystemImage.objects.all()
          return(generics.ListAPIView.get(self, request, format=None))
        # choose a random jobserver
        js_set = list(image.jobservers.all())
        js = None
        if(len(js_set)==0):
          # if there are no jobservers, return 404
          raise NotFound(detail="Error 404, No Jobservers for Image", code=404) 
        print(js_set)
        js = random.choice(js_set)
        imageURL = "http://" + js.address + "/" + image.slug + ".vmlinuz"

        return redirect(imageURL)        

class SytemImageDetailsAPIView(MProvView, mixins.RetrieveModelMixin,
                      GenericAPIView):
  model = SystemImage
  queryset = SystemImage.objects.all()
  serializer_class = SystemImageSerializer
  
  def get(self, request, format=None, **kwargs):
    return self.retrieve(self, request, format=None, **kwargs)


class SytemImageUpdateAPIView(MProvView, mixins.RetrieveModelMixin,
                      GenericAPIView):
  model = SystemImage
  queryset = SystemImage.objects.all()
  serializer_class = SystemImageUpdateSerializer
 