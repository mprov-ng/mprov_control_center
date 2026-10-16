from django.urls import path
from jobqueue.views import JobModulesAPIView, JobStatusChangesView

app_name = 'jobqueue'

urlpatterns = [
    # status-changes/ comes first so the <str:pk> route doesn't swallow it.
    path('status-changes/', JobStatusChangesView.as_view(), name='job_status_changes'),
    path('<str:pk>/', JobModulesAPIView.as_view()),
    path('', JobModulesAPIView.as_view()),
]
