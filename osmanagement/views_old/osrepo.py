from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from osmanagement.models import OSRepo


@api_view(["GET"])
def APIOSRepooView(request, *args, **kwargs):
  print(request.content_type)
  # we are only letting json into the api.
  if(request.content_type != 'application/json'):
    return OSRepoListView(request, *args, **kwargs)
  
  model_data = list(OSRepo.objects.all().values())
  data=[]
  if model_data:
    data = model_data
  return Response(data)

def OSRepoListView(request, *args, **kargs):
  return HttpResponse("Distrubution List")