from django.urls import path, re_path
from osmanagement.views_noath import OSRepoURLAPIView

# This file is the no authed, webpage/redirect for the osrepos/ in the mPCC

urlpatterns = [
    path('<int:pk>/', OSRepoURLAPIView.as_view()),
    re_path(r'(?P<pk>[0-9]+)/(?P<redirect_url>.*)$', OSRepoURLAPIView.as_view()),
    path('', OSRepoURLAPIView.as_view()),
    
]