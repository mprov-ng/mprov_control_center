from django.urls import path
from jobqueue.views import JobModulesAPIView, JobStatusChangesView

app_name = 'jobqueue'

urlpatterns = [
    path('<int:pk>/', JobModulesAPIView.as_view()),
    path('', JobModulesAPIView.as_view()),
    path('status-changes/', JobStatusChangesView.as_view(), name='job_status_changes'),
]
