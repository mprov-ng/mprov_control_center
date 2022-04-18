from django.forms.models import model_to_dict
from django.shortcuts import render
import json
from rest_framework.response import Response
from rest_framework.decorators import api_view
from systems.models import Switch, SwitchPort, System


@api_view(["GET"])
def APISwitchView(request, *args, **kwargs):
  model_data = Switch.objects.all().values()
  data = []
  if model_data:
    data = model_data    
  return Response(data)

@api_view(["GET"])
def APISystemView(request, *args, **kwargs):
  model_data = list(System.objects.all().values())
  data=[]
  if model_data:
    data = model_data
  return Response(data)