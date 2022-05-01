from django.urls import path
from .views import NetworkInterfaceDetailAPIView, NetworkInterfaceAPIView

urlpatterns = [
    path('<str:pk>/', NetworkInterfaceAPIView.as_view()),
    path('<str:pk>/details', NetworkInterfaceDetailAPIView.as_view()),
    #path('<str:pk>/update', NetworkInterfaceUpdateAPIView.as_view()),
    path('', NetworkInterfaceAPIView.as_view()),
]