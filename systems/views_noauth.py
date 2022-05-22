
from .models import SystemImage
from django.shortcuts import redirect
from rest_framework.exceptions import NotFound
import random
from common.views import MProvView
from systems.serializers import SystemImageSerializer
from rest_framework import generics
from django.http import HttpResponseNotAllowed


class SystemImageAPIView(MProvView, generics.ListAPIView):
    '''
# /images/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /images/compute/)


## Documentation

### Class Attributes
- slug: a machine parsable version of the name
- name: A human readable name

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:



### GET (with primary key)
    - Will return the image requested, regardless of requested content type.

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
        self.queryset = SystemImage.objects.all()
        return(generics.ListAPIView.get(self, request, format='json'))
      # choose a random jobserver
      js_set = list(image.jobservers.all())
      js = None
      if(len(js_set)==0):
        # if there are no jobservers, return 404
        raise NotFound(detail="Error 404, No Jobservers for Image", code=404) 
      print(js_set)
      js = random.choice(js_set)
      imageURL = "http://" + js.address + ":" + str(js.port) + "/" + image.slug
      if isInitRamFS:
        imageURL += ".initramfs"
      else:
        imageURL += ".img"
      return redirect(imageURL)
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
NOTE: This is a mimic of the /image/ function but specifically for serving 
kernels to PXE.  This function may be merged into /images/ at some point.


## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /kernels/compute/)


## Documentation

### Class Attributes
- slug: a machine parsable version of the name
- name: A human readable name

### GET method (no parameters)
Returns a json list of all objects in the MPCC of this type

Format returned:



### GET (with primary key)
    - Will return the image requested, regardless of requested content type.

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
          image = SystemImage.objects.get(pk=kwargs['pk'])
        else: 
          result = self.checkContentType(request, format=format, kwargs=kwargs)
          if result is not None:
              return result 
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
        imageURL = "http://" + js.address + ":" + str(js.port) + "/" + image.slug + ".vmlinuz"

        return redirect(imageURL)        
      def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

      def delete(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def put(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def patch(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])