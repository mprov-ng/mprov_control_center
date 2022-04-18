from django.urls import path
from jobqueue.views import JobServersAPIView

urlpatterns = [
    path('<int:pk>/', JobServersAPIView.as_view()),
    path('', JobServersAPIView.as_view()),
]