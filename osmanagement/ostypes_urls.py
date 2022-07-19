from django.urls import path
from osmanagement.views import OSTypeAPIView

urlpatterns = [
    path('<str:pk>/', OSTypeAPIView.as_view()),
    path('', OSTypeAPIView.as_view()),
]