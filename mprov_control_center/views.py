from common.views import MProvView
from django.apps import apps
from rest_framework.response import Response
from rest_framework import serializers
from django.views import View
from django.http import JsonResponse
# Default view for the index.
class IndexAPIView(MProvView):
    """
# Welcome to mProv Control Center

Welcome to the mProv Control Center API.  What you see here is the documentation for how mPCC's RESTful API works.


Chances are good you are looking for the [Admin](/admin/) section to get in and modify stuff.  If, 
however, you are looking for the documentation on how to use this API, you should probably try clicking on 
one of the following links.   Each link is a section of the API that corresponds to a section of the admin 
interface.  It will give you documentation on how to use that section of the API.

* [/ansiblecollection/](/ansiblecollection/)
* [/ansibleplaybook/](/ansibleplaybook/)
* [/ansiblerole/](/ansiblerole/)
* [/distros/](/distros/)
* [/files/](/files/)
* [/images/](/images/)
* [/jobs/](/jobs/)
* [/jobmodules/](/jobmodules/)
* [/jobservers/](/jobservers/)
* [/networkinterfaces/](/networkinterfaces/)
* [/networks/](/networks/)
* [/networktypes/](/networktypes/)
* [/osrepos/](/osrepos/)
* [/ostypes/](/ostypes/)
* [/repos/](/repos/)
* [/scripts/](/scripts/)
* [/switches/](/switches/)
* [/switchports/](/switchports/)
* [/systembmcs/](/systembmcs/)
* [/systemgroups/](/systemgroups/)
* [/systemimages/](/systemimages/)
* [/systems/](/systems/)
* [/systems/register](/systems/register)


    """
    authentication_classes = [] #disables authentication
    permission_classes = [] #disables permission

class DataTypeView(View):
    """
    Returns the JSON field structure of the model named in the ?model= query
    parameter (e.g. ?model=jobqueue.models.Job), or, with no ?model=, a list
    of all registered non-Django data models.
    """
   
    def get(self, request, format=None, **kwargs):
        model_list = []
        for model in apps.get_models():
            full_class_name = model.__module__ + "." + model.__name__ 
            if full_class_name.startswith('django') or full_class_name.startswith('rest_framework'):
                continue
            model_list.append(full_class_name)
        if 'model' in request.GET:
            self.model = request.GET['model']
            if self.model not in model_list:
                self.model = None
                return JsonResponse({'error': 'Unknown Model Requested'}, status=500)
        else:
            self.model = None
   

        if self.model == None:
            return JsonResponse({'datamodels': model_list})
        return JsonResponse(MProvView().getJSONDataStructure(self.model))