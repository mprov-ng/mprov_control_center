import imp
from .models import SystemImage
from rest_framework.views import APIView
from django.shortcuts import redirect
from rest_framework import mixins
from rest_framework.generics import GenericAPIView
from common.views import MProvView
from systems.serializers import SystemImageSerializer
from osmanagement.models import OSDistro, OSRepo
from rest_framework.response import Response


class SystemImageAPIView(APIView):
      model = SystemImage
      # TODO: placeholder for now to test 302 redirects
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      def get(self, request, format=None, *args, **kwargs):
        return redirect("http://imsrv.test.cluster/static/initrd.img")


class SytemImageDetailsAPIView(MProvView, mixins.RetrieveModelMixin,
                      GenericAPIView):
  queryset = SystemImage.objects.all()
  serializer_class = SystemImageSerializer
  def get(self, request, format=None, **kwargs):
    return self.retrieve(self, request, format=None, **kwargs)

