from django.urls import path
from scripts.views import ScriptAPIView

urlpatterns = [
    path('<int:pk>/', ScriptAPIView.as_view()),
    path('', ScriptAPIView.as_view()),
]