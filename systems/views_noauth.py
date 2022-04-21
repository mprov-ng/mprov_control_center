from .models import SystemImage
from rest_framework.views import APIView
from django.shortcuts import redirect

class SystemImageAPIView(APIView):
      model = SystemImage
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      def get(self, request, format=None, *args, **kwargs):
        return redirect("/static/initrd.img")
