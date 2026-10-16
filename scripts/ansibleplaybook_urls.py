from django.urls import path
from scripts.views import AnsiblePlaybookAPIView

urlpatterns = [
    path('<str:pk>/', AnsiblePlaybookAPIView.as_view()),
    path('', AnsiblePlaybookAPIView.as_view()),
]
