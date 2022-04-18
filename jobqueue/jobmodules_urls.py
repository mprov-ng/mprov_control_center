from django.urls import path
from jobqueue.views import JobModulesAPIView

urlpatterns = [
    path('<str:pk>/', JobModulesAPIView.as_view()),
    path('', JobModulesAPIView.as_view()),
]