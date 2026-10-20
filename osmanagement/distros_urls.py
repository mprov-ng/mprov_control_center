from django.urls import path
from osmanagement.views import OSDistroAPIView

urlpatterns = [
    path('<int:pk>/', OSDistroAPIView.as_view()),
    path('', OSDistroAPIView.as_view()),
]