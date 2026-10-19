from django.urls import path
from scripts.views import ScriptAPIView

urlpatterns = [
    path('<str:pk>/', ScriptAPIView.as_view()),
    path('', ScriptAPIView.as_view()),
]