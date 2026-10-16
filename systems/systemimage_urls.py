from django.urls import path
from systems.views import SystemImagesAPIView

urlpatterns = [
    path('<str:pk>/', SystemImagesAPIView.as_view()),
    path('<str:pk>/details', SystemImagesAPIView.as_view()),
    path('<str:pk>/update', SystemImagesAPIView.as_view()),
    path('', SystemImagesAPIView.as_view()),
]