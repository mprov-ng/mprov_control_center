from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from osmanagement.models import OSDistro

@api_view(["GET"])
def APIOSDistroView(request, *args, **kwargs):
  print(request.content_type)
  # we are only letting json into the api.
  if(request.content_type != 'application/json'):
    return OSDistroListView(request, *args, **kwargs)
  
  model_data = list(OSDistro.objects.all().values())
  data=[]
  if model_data:
    data = model_data
  return Response(data)

def OSDistroListView(request, *args, **kargs):
  return HttpResponse("Distrubution List")