from django.urls import path
from osmanagement.views import OSDistroAPIView, OSRepoAPIView

urlpatterns = [
    path('<int:pk>/', OSDistroAPIView.as_view()),
    path('', OSDistroAPIView.as_view()),
]