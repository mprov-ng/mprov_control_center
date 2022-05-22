from django.urls import path
from systems.views_noauth import SystemImageAPIView
from systems.views import SytemImageDetailsAPIView, SytemImageUpdateAPIView

urlpatterns = [
    path('<str:pk>/', SystemImageAPIView.as_view()),
    path('<str:pk>/details', SytemImageDetailsAPIView.as_view()),
    path('<str:pk>/update', SytemImageUpdateAPIView.as_view()),
    path('', SystemImageAPIView.as_view()),
]