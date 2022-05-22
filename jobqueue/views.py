from datetime import datetime
from common.views import MProvView
from jobqueue.models import JobModule, JobServer, Job
from jobqueue.serializers import JobAPISerializer, JobModuleAPISerializer, JobServerAPISerializer
from rest_framework import status, generics
from rest_framework.response import Response
from django.shortcuts import render
from django.core.serializers import serialize
import json

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework import mixins
from rest_framework.generics import GenericAPIView

class JobAPIView(MProvView,
                      GenericAPIView):
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
    model = JobModule
    template = "jobmodules_docs.html"
    serializer_class = JobModuleAPISerializer
    queryset = JobModule.objects.all()
    search_fields =['name', 'slug']


class JobServersAPIView(MProvView):
    model = JobServer
    template = "jobservers_docs.html"
    serializer_class = JobServerAPISerializer

    # TODO: Redefine post to create_or_update.
    
    def post(self, request, format=None):
        if 'port' not in request.data:
            request.data['port'] = None
        defaults = {
            'heartbeat_time': datetime.now(),
            'address': request.data['address'],
            'name': request.data['name'],
            'port': request.data['port']
        }
        data = {}
        if request.data['name']:
            obj, created = JobServer.objects.update_or_create(
                name=request.data['name'],
                defaults=defaults,
                
            )
            if obj is not None:
                for i in request.data['jobmodules']:
                    # look up the jobmodule
                    obj.jobmodules.add(JobModule.objects.get(pk=i))
            obj.save()
        data['pk'] = obj.pk
        return Response(status=status.HTTP_200_OK,data=json.dumps(data))
