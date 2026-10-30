from datetime import datetime
from common.views import MProvView
from jobqueue.models import JobModule, JobServer, Job, filter_params
from jobqueue.serializers import JobAPISerializer, JobModuleAPISerializer, JobServerAPISerializer
from rest_framework import status, generics
from rest_framework.response import Response
import json

from rest_framework.generics import GenericAPIView
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views import View

# Optional API behaviours this mPCC supports, listed in the POST /jobservers/
# reply so a job server only relies on them when they're there (#406).  Add
# a name here when a client needs to detect a new behaviour.
# - addjs-version: PATCH /systemimages/<slug>/?addjs accepts "version" (#396).
# - host-id: POST /jobservers/ accepts "host_id" and finds the job server by
#   it, so a rename keeps the same row (mprov_jobserver#113).
FEATURES = ["addjs-version", "host-id"]

class JobAPIView(MProvView,
                      GenericAPIView):
    '''
# /jobs/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /jobs/1/)
- POST (no primary key, e.g. /jobs/)
- PATCH (with primary key, e.g. /jobs/1/)
- DELETE (with primary key, e.g. /jobs/1/)

## Documentation

### Class Attributes
- id: Internal ID 
- name: Human-readable name for the job
- create_time: (Auto) Time the job was created
- start_time: (Optional) Time the job is started, set by jobserver
- end_time: (Optional) Time the job finished, set by the jobserver
- last_update: (Auto) Time of the last modification
- return_code: (Optional) Any return code from the job
- params: (Optional) Any params for the job, in JSON
- module: ID of the job module this job is defined as
- status: ID of the current status of the job.
- jobserver: (Optional) ID of the job server currently assigned to this job

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC.  The list can be
filtered with these optional query parameters:

- module: A job module ID, or a JSON array of job module IDs (e.g. ?module=["repo-update","pxe-update"])
- params: A JSON object (e.g. ?params={"imageId":"compute"}); only jobs whose params
    have each of its keys set to that value are returned.  Anything else returns 400.
- jobserver: ID of the assigned job server
- status: ID of the job's status
- search: a job module ID to search for

Any other query parameter returns 400.

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

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST is sent to the base URL (no primary
    key) and will Create a new entry; it requires ALL required fields.  PATCH
    will only update the fields passed; fields that are not changing can be omitted.

- GET returns the object specified or 404

- POST returns the new object created, or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = Job
    serializer_class = JobAPISerializer
    queryset = Job.objects.all()
    search_fields = ['module__slug']
    extra_query_params = ('module', 'params', 'jobserver', 'status')

    # Override the default get func; we need a bit more specialized query here
    def get(self, request, format=None, **kwargs):
        result = self.checkContentType(request, format=format)
        if result is not None:
            return result
        
        # if we are 'application/json' return an empty 200 response if
        # model is not set.
        if self.model is None:
            return Response(None)
        
        if 'pk' in kwargs:
            # someone is looking for a specific item.
            return self.retrieve(request, pk=kwargs['pk'])

        # Let's see if someone is looking for something specific.  Only the
        # keys below are filters; anything else is a 400, not ignored (#390).
        error_body = {field: self.unknown_query_param(field)
                      for field in request.query_params if not self.is_extra_query_param(field)}
        if len(error_body) > 0:
            return Response(error_body, status=400)
        queryset = self.model.objects.all()
        jobmodule = self.request.query_params.get('module')
        
        if jobmodule is not None:
            if jobmodule.startswith("["):
                # we are being passed an array
                # convert the string to an array
                try:
                    modules = json.loads(jobmodule)
                except ValueError:
                    modules = None
                if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules):
                    return Response({'module': "Must be a job module ID or a JSON array of them, e.g. [\"repo-update\",\"pxe-update\"]."}, status=400)
                queryset = queryset.filter(module__in=modules)
            else:
                queryset = queryset.filter(module=jobmodule)
        params = self.request.query_params.get('params')
        if params is not None:
            # match each key of a JSON object against the job's params.
            try:
                params = json.loads(params)
            except ValueError:
                params = None
            if not isinstance(params, dict):
                return Response({'params': "Must be a JSON object, e.g. {\"imageId\": \"compute\"}."}, status=400)
            queryset = filter_params(queryset, params)
        jobserver = self.request.query_params.get('jobserver')
        if jobserver is not None:
            queryset = queryset.filter(jobserver=jobserver)
        status = self.request.query_params.get('status')
        if status is not None:
            queryset = queryset.filter(status=status)
        
        self.queryset=queryset
        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None)


class JobModulesAPIView(MProvView):
    '''
# /jobmodules/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /jobmodules/pxe-update/)
- POST (no primary key, e.g. /jobmodules/)
- PATCH (with primary key, e.g. /jobmodules/pxe-update/)
- DELETE (with primary key, e.g. /jobmodules/pxe-update/)

## Documentation

### Class Attributes
- slug: The ID of the job module
- name: A human-readable name for the job module
- active: Unused, will be removed in future updates
    
### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

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

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  POST is sent to the base URL (no primary
    key) and will Create a new entry; it requires ALL required fields.  PATCH
    will only update the fields passed; fields that are not changing can be omitted.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST returns the new object created, or a 400 error if validation fails

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = JobModule
    serializer_class = JobModuleAPISerializer
    queryset = JobModule.objects.all()
    search_fields =['name', 'slug']


class JobServersAPIView(MProvView):
    '''
# /jobservers/

## Accepted HTTP Methods:
- GET (no primary key)
- GET (with Primary Key, e.g. /jobservers/1/)
- POST (no primary key, e.g. /jobservers/)
- PATCH (with primary key, e.g. /jobservers/1/)
- DELETE (with primary key, e.g. /jobservers/1/)

## Documentation

### Class Attributes
- id: The internal ID of the job server
- name: The hostname of the job server
- address: The IP address of the jobserver
- port: The port the job server listens on
- heartbeat_time: The time of the last heartbeat from the job server
- jobmodules: array of job module IDs that this job server handles.
- one_minute_load: The job server's 1 minute load average
- network: (Optional) ID of the network the job server is on.  POST ignores it;
    set it with PATCH.

    
### Query Parameters
- ?detail: GET (no primary key) returns entries with related objects nested 3 levels deep, as for a single entry.

### GET method (no primary key)
Returns a JSON list of all objects of this type in the mPCC, or 404 if there are
none.  Any field of this type can be passed as a query parameter to filter the
list (e.g. ?name=example).

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
        "port": 8080,
        "heartbeat_time": "2022-05-16T13:56:42.321346-05:00",
        "jobmodules": [
            "nads",
            "script-runner"
        ]
    }
    ]

### GET, PATCH, DELETE (with primary key) and POST (without primary key)
- GET, PATCH, and DELETE, when passed a primary key, will Retrieve, Update, or
    Delete that entry in the database.  PATCH will only update the fields passed;
    fields that are not changing can be omitted.

- GET returns the object specified, with related objects nested 3 levels deep, or 404

- POST is sent to the base URL (no primary key) and creates or updates the job
    server.  It requires name, address, one_minute_load, and jobmodules (a list
    of job module IDs to register); port is optional and defaults to 8080.
    host_id is optional: with it, the job server is found by host_id, so a new
    name renames the same job server; a job server registered under that name
    without a host_id is adopted.  Without it, the job server with the given
    name is updated.  It returns 200 with the job server's ID and the optional
    API features this mPCC supports, as a JSON-encoded string, e.g.
    '{"pk": 3, "features": ["addjs-version", "host-id"]}' (a client ignores
    feature names it doesn't know), 400 if a required field is missing, the
    name is blank or host_id isn't a non-blank string of up to 64 characters,
    409 if host_id is sent and the name belongs to a different job server, or
    a 500 error if a job module can't be found.

- PATCH returns the updated object.

- DELETE returns 204 No Content if the delete is successful.

    '''
    model = JobServer
    serializer_class = JobServerAPISerializer

    # Redefine post to create_or_update.
    
    def post(self, request, format=None):
        missing = [field for field in ('name', 'address', 'one_minute_load', 'jobmodules') if field not in request.data]
        if missing:
            return Response({field: "This field is required." for field in missing}, status=status.HTTP_400_BAD_REQUEST)
        if not request.data['name']:
            return Response({'name': "This field may not be blank."}, status=status.HTTP_400_BAD_REQUEST)
        # bad types used to fail inside update_or_create() or the jobmodules
        # loop with a 500 (#328).
        errors = {}
        try:
            float(request.data['one_minute_load'])
        except (TypeError, ValueError):
            errors['one_minute_load'] = "Must be a number."
        if request.data.get('port') is not None:
            try:
                int(request.data['port'])
            except (TypeError, ValueError):
                errors['port'] = "Must be an integer."
        if not isinstance(request.data['jobmodules'], list):
            errors['jobmodules'] = "Must be a list of job module IDs."
        host_id = request.data.get('host_id')
        if 'host_id' in request.data and not (isinstance(host_id, str) and 0 < len(host_id.strip()) <= 64):
            errors['host_id'] = "Must be a non-blank string of up to 64 characters."
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
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
        if defaults['port'] is None:
            defaults['port'] = 8080
        if host_id is None:
            # job servers without a host ID are known by name, as before.
            obj, created = JobServer.objects.update_or_create(
                name=request.data['name'],
                defaults=defaults,
            )
        else:
            obj, conflict = self._register_by_host_id(host_id.strip(), defaults)
            if conflict:
                return Response({"detail": conflict}, status=status.HTTP_409_CONFLICT)
        for i in request.data['jobmodules']:
            # look up the jobmodule
            try:
                obj.jobmodules.add(JobModule.objects.get(pk=i))
            except JobModule.DoesNotExist:
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data=json.dumps({"msg": f"Error locating jobmodule: {i}"}))
        obj.save()
        data['pk'] = obj.pk
        data['features'] = FEATURES
        return Response(status=status.HTTP_200_OK,data=json.dumps(data))

    def _register_by_host_id(self, host_id, defaults):
        """
        Create or update the job server with this host ID (mprov_jobserver#113).
        A rename keeps the same row.  A row with the requested name and no host
        ID (the same job server before it sent one) is adopted.  Returns
        (job server, None), or (None, reason) when the name belongs to a
        different job server.
        """
        name = defaults['name']
        conflict = f"name {name} is registered by another job server"
        with transaction.atomic():
            obj = JobServer.objects.select_for_update().filter(host_id=host_id).first()
            named = JobServer.objects.select_for_update().filter(name=name).first()
            if named is not None and named != obj:
                if obj is not None or named.host_id is not None:
                    return None, conflict
                obj = named
            if obj is None:
                obj = JobServer(host_id=host_id)
            obj.host_id = host_id
            for field, value in defaults.items():
                setattr(obj, field, value)
            try:
                with transaction.atomic():
                    obj.save()
            except IntegrityError:
                # another request registered this name or host ID meanwhile.
                return None, conflict
        return obj, None


class JobStatusChangesView(View):
    """
    View to retrieve recent job status changes for toast notifications.
    Only admin users (staff) can see them; anyone else gets 403.
    """
    def get(self, request):
        if not (request.user.is_active and request.user.is_staff):
            return JsonResponse({'detail': "Authentication required."}, status=403)
        # Get recent job status changes from cache
        
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
