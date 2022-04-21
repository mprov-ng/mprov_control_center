from django.urls import path
from systems.views_noauth import SystemImageAPIView

urlpatterns = [
    path('<str:pk>/', SystemImageAPIView.as_view()),
    path('', SystemImageAPIView.as_view()),
]