from .models import SystemImage
from rest_framework.views import APIView
from django.shortcuts import redirect

class SystemImageAPIView(APIView):
      model = SystemImage
      # TODO: placeholder for now to test 302 redirects
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      def get(self, request, format=None, *args, **kwargs):
        return redirect("/static/initrd.img")
