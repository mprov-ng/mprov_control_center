from django.urls import path
from osmanagement.views import OSDistroAPIView, OSRepoAPIView

# This file is the API endpoint for the repos/ in the mPCC

urlpatterns = [
    path('<int:pk>/', OSRepoAPIView.as_view()),
    path('', OSRepoAPIView.as_view()),
]