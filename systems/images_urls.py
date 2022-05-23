from django.urls import path
from systems.views_noauth import ImagesAPIView

urlpatterns = [
    path('<str:pk>/', ImagesAPIView.as_view()),
    path('', ImagesAPIView.as_view()),
]