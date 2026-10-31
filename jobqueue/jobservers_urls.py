from django.urls import path
from jobqueue.views import JobServersAPIView, JobServerAddressHeartbeatAPIView

urlpatterns = [
    path('<int:pk>/heartbeat/', JobServerAddressHeartbeatAPIView.as_view()),
    path('<int:pk>/', JobServersAPIView.as_view()),
    path('', JobServersAPIView.as_view()),
]
