from django.urls import path
from jobqueue.views import JobAPIView

urlpatterns = [
    path('<int:pk>/', JobAPIView.as_view()),
    path('', JobAPIView.as_view()),
]