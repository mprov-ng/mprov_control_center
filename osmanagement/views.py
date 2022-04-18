from common.views import MProvView
from osmanagement.models import OSDistro, OSRepo
from osmanagement.serializers import OSDistroAPISerializer, OSRepoAPISerializer
from jobqueue.models import Job, JobModule
from mprov.common.jobqueue import JobType
from pprint import pprint

class OSDistroAPIView(MProvView):
    model = OSDistro 
    template = 'osdistro_docs.html'
    serializer_class = OSDistroAPISerializer
    queryset = OSDistro.objects.all()

class OSRepoAPIView(MProvView):
    model = OSRepo
    template = 'osrepo_docs.html'