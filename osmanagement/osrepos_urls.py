from django.urls import path
from osmanagement.views_noath import OSRepoURLAPIView

# This file is the no authed, webpage/redirect for the osrepos/ in the mPCC

urlpatterns = [
    path('<int:pk>/', OSRepoURLAPIView.as_view()),
    path('', OSRepoURLAPIView.as_view()),
]