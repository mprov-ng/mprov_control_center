from django.urls import path
from scripts.views import AnsibleRoleAPIView

urlpatterns = [
    path('<str:pk>/', AnsibleRoleAPIView.as_view()),
    path('', AnsibleRoleAPIView.as_view()),
]
