
from .models import SystemImage
from django.shortcuts import redirect
from rest_framework.exceptions import NotFound
import random
from common.views import MProvView
from systems.serializers import SystemImageSerializer
from rest_framework import generics
from django.http import HttpResponseNotAllowed


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
        # No primary key specified and requesting JSON,
        # in this instance, we will 404
        raise NotFound(detail="Error 404, No Jobservers for Image", code=404) 
      # choose a random jobserver
      js_set = list(image.jobservers.all())
      js = None
      if(len(js_set)==0):
        # if there are no jobservers, return 404
        raise NotFound(detail="Error 404, No Jobservers for Image", code=404) 
      print(js_set)
      js = random.choice(js_set)
      imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug 
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
NOTE: This is a mimic of the /images/ function but specifically for serving 
kernels to PXE.  This function may be merged into /images/ at some point.


## Accepted HTTP Methods:
- GET (with Primary Key, ie: /kernels/compute/)

## Documentation

### Class Attributes
Note: See [/images/](/images/)

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
        imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug + ".vmlinuz"

        return redirect(imageURL)        
      def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

      def delete(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def put(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def patch(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])