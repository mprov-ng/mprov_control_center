from django.urls import path
from systems.views_noauth import KernelImageAPIView

urlpatterns = [
    path('<str:pk>/', KernelImageAPIView.as_view()),
    # path('<str:pk>/details', SytemImageDetailsAPIView.as_view()),
    # path('<str:pk>/update', SytemImageUpdateAPIView.as_view()),
    path('', KernelImageAPIView.as_view()),
]