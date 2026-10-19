from django.urls import path
from scripts.views import FileAPIView

urlpatterns = [
    path('<str:pk>/', FileAPIView.as_view()),
    path('', FileAPIView.as_view()),
]
