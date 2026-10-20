from django.urls import path
from osmanagement.views import OSRepoAPIView

# This file holds the API endpoints for repos/ in the mPCC

urlpatterns = [
    path('<int:pk>/', OSRepoAPIView.as_view()),
    path('', OSRepoAPIView.as_view()),
]