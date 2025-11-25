from datetime import datetime
from common.views import MProvView
from jobqueue.models import JobModule, JobServer, Job
from jobqueue.serializers import JobAPISerializer, JobModuleAPISerializer, JobServerAPISerializer
from rest_framework import status, generics
from rest_framework.response import Response
import json

from rest_framework.generics import GenericAPIView
from django.core.cache import cache
from django.http import JsonResponse
from django.views import View

class JobAPIView(MProvView,
                      GenericAPIView):
    '''
# /jobs/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /jobs/1/)
- POST (with primary key, ie: /jobs/1/)
- PATCH (with primary key, ie: /jobs/1/)
- DELETE (with primary key, ie: /jobs/1/)

## Documentation

### Class Attributes
- id: Internal ID 
- name: Human readable name for the job
- create_time: (Auto) Time the job was created
- start_time: (Optional) Time the job is started, set by jobserver
- end_time: (Optional) Time the job finished, set by the jobserver
- last_update: (Auto) Time of the last modification
- return_code: (Optional) Any return code from the job
- params: (Optional) Any params for the job, in JSON
- module: ID of the job module this job is defined as
- status: ID of the current status of the job.
- jobserver: (Optional) ID of the job server currently assigned to this job

### GET method (no parameters)
Returns a json list of all objects of this type in the MPCC

Format returned:

    [
    {
        "id": 1,
        "name": "Update Repos",
        "create_time": "2022-05-10T11:54:10.765443-05:00",
        "start_time": null,
        "end_time": null,
        "last_update": "2022-05-10T11:54:10.765475-05:00",
        "return_code": null,
        "params": {},
        "module": "repo-update",
        "status": 1,
        "jobserver": null
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = Job
    template = "jobs_docs.html"
    serializer_class = JobAPISerializer
    queryset = Job.objects.all()
    search_fields = ['module__slug']

    # Override the default get func, we need a bit more specialized query here
    def get(self, request, format=None, **kwargs):
        result = self.checkContentType(request, format=format)
        if result is not None:
            return result
        
        # if we are 'application/json' return an empty dict if
        # model is not set.
        if self.model == None:
            return Response(None)
        
        if 'pk' in kwargs:
            # someone is looking for a specific item.
            return self.retrieve(self, request, format=None, pk=kwargs['pk'])

        # Let's see if someone is looking for something specific.
        queryset = self.model.objects.all()
        jobmodule = self.request.query_params.get('module')
        
        if jobmodule is not None:
            # print(jobmodule)
            if jobmodule[0] == "[":
                # we are being passed an array
                # convert the string to an array
                modules = json.loads(jobmodule) 
                queryset = queryset.filter(module__in=modules)
            else:
                queryset = queryset.filter(module=jobmodule)
        params = self.request.query_params.get('params')
        # print(params)
        if params is not None:
            queryset = queryset.filter(params__contains=[(params)])
        jobserver = self.request.query_params.get('jobserver')
        if jobserver is not None:
            queryset = queryset.filter(jobserver=jobserver)
        status = self.request.query_params.get('status')
        if status is not None:
            queryset = queryset.filter(status=status)
        
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);


class JobModulesAPIView(MProvView):
    '''
# /jobmodules/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /jobmodules/1/)
- POST (with primary key, ie: /jobmodules/1/)
- PATCH (with primary key, ie: /jobmodules/1/)
- DELETE (with primary key, ie: /jobmodules/1/)

## Documentation

### Class Attributes
- slug: The ID of the job module
- name: A human readable name for the job module
- active: Unused, will be removed in future updates
    
### GET method (no parameters)
Returns a json list of all objects of this type in the MPCC

Format returned:

    [
    {
        "slug": "pxe-update",
        "name": "PXE Update",
        "active": 0
    },
    {
        "slug": "pxe-delete",
        "name": "PXE Delete",
        "active": 0
    },
    {
        "slug": "dns-update",
        "name": "DNS Update",
        "active": 0
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = JobModule
    template = "jobmodules_docs.html"
    serializer_class = JobModuleAPISerializer
    queryset = JobModule.objects.all()
    search_fields =['name', 'slug']


class JobServersAPIView(MProvView):
    '''
# /jobservers/

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /jobservers/1/)
- POST (with primary key, ie: /jobservers/1/)
- PATCH (with primary key, ie: /jobservers/1/)
- DELETE (with primary key, ie: /jobservers/1/)

## Documentation

### Class Attributes
- id: The internal ID of the job server
- name: The hostname of the job server
- address: The IP address of the jobserver
- port: What port is the job server on
- heartbeat_time: The last time of the last heartbeat from the job server
- jobmodules: array of job module IDs that this job server handles.

    
### GET method (no parameters)
Returns a json list of all objects of this type in the MPCC

Format returned:

    [
    {
        "id": 3,
        "name": "localhost.localdomain",
        "address": "172.16.1.1",
        "port": 8080,
        "heartbeat_time": "2022-05-19T14:42:41.942121-05:00",
        "jobmodules": [
            "dnsmasq",
            "image-delete",
            "image-server",
            "image-update"
        ]
    },
    {
        "id": 4,
        "name": "ip172016254054.vpn.jhu.edu",
        "address": "172.16.254.54",
        "port": null,
        "heartbeat_time": "2022-05-16T13:56:42.321346-05:00",
        "jobmodules": [
            "nads",
            "script-runner"
        ]
    }
    ]

### GET, POST, PATCH, DELETE (with primary key)
- These methods, when passed a primary key, will Retrieve, Create, Update, or 
    Delete that entry in the database.  POST requires ALL required fields.  PATCH
    will only update the fields passed, required fields can be omitted if changed.

- GET returns the object specified or 404

- POST returns the new object created or a 500 style error

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = JobServer
    template = "jobservers_docs.html"
    serializer_class = JobServerAPISerializer

    # Redefine post to create_or_update.
    
    def post(self, request, format=None):
        if 'port' not in request.data:
            request.data['port'] = None
        defaults = {
            'heartbeat_time': datetime.now(),
            'address': request.data['address'],
            'name': request.data['name'],
            'port': request.data['port'],
            'one_minute_load': request.data['one_minute_load']
        }
        data = {}
        if defaults['port'] == None:
            defaults['port'] = 8080
        if request.data['name']:
            obj, created = JobServer.objects.update_or_create(
                name=request.data['name'],
                defaults=defaults,
                
            )
            if obj is not None:
                for i in request.data['jobmodules']:
                    # look up the jobmodule
                    try:
                        obj.jobmodules.add(JobModule.objects.get(pk=i))
                    except :
                        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data=json.dumps({"msg": f"Error locating jobmodule: {i}"}))
            obj.save()
        data['pk'] = obj.pk
        return Response(status=status.HTTP_200_OK,data=json.dumps(data))


class JobStatusChangesView(View):
    """
    View to retrieve recent job status changes for toast notifications.
    """
    def get(self, request):
        # Get recent job status changes from cache
        from django.core.cache import cache
        
        recent_changes_key = "recent_job_status_changes"
        recent_changes = cache.get(recent_changes_key, [])
        
        # Retrieve the actual change data for each key
        changes = []
        processed_keys = []
        
        for change_key in recent_changes:
            change_data = cache.get(change_key)
            if change_data:
                changes.append(change_data)
                processed_keys.append(change_key)
        
        # Update the recent changes list to only include keys we still have data for
        if len(processed_keys) < len(recent_changes):
            cache.set(recent_changes_key, processed_keys, 300)
        
        return JsonResponse({'changes': changes})
