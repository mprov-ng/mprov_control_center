from django.urls import path
from scripts.views import AnsibleCollectionAPIView

urlpatterns = [
    path('<str:pk>/', AnsibleCollectionAPIView.as_view()),
    path('', AnsibleCollectionAPIView.as_view()),
]
