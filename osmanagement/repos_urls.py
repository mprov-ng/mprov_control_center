from django.urls import path
from osmanagement.views import OSDistroAPIView, OSRepoAPIView

urlpatterns = [
    path('<int:pk>/', OSRepoAPIView.as_view()),
    path('', OSRepoAPIView.as_view()),
]