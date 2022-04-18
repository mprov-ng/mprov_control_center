from datetime import datetime
from common.views import MProvView
from jobqueue.models import JobModule, JobServer, Job
from jobqueue.serializers import JobAPISerializer, JobModuleAPISerializer, JobServerAPISerializer
from rest_framework import status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

class JobAPIView(MProvView):
    model = Job
    template = "jobs_docs.html"
    serializer_class = JobAPISerializer
    queryset = Job.objects.all()
    search_fields = ['module__slug']


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
        defaults = {
            'heartbeat_time': datetime.now(),
            'address': request.data['address'],
            'name': request.data['name']
        }
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
        return Response(status=status.HTTP_200_OK)
