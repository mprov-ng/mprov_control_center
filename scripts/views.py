from django.shortcuts import render
from common.views import MProvView
from .models import Script
from .serializers import ScriptAPISerializer

class ScriptAPIView(MProvView):
  model = Script
  template = "scripts_docs.html"
  serializer_class = ScriptAPISerializer
  queryset = Script.objects.all()
