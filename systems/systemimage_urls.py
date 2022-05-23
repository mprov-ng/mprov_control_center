from django.urls import path
from systems.views import SytemImagesAPIView

urlpatterns = [
    path('<str:pk>/', SytemImagesAPIView.as_view()),
    path('<str:pk>/details', SytemImagesAPIView.as_view()),
    path('<str:pk>/update', SytemImagesAPIView.as_view()),
    path('', SytemImagesAPIView.as_view()),
]