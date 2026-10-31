from django.urls import path
from jobqueue.views import JobAPIView, JobClaimAPIView

urlpatterns = [
    path('<int:pk>/claim/', JobClaimAPIView.as_view()),
    path('<int:pk>/', JobAPIView.as_view()),
    path('', JobAPIView.as_view()),
]