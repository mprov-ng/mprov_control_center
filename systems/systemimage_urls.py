from django.urls import path
from systems.views import SystemImagesAPIView
from systems.views_files import SystemImageFileView

urlpatterns = [
    path('<str:pk>/files/<str:slug>/', SystemImageFileView.as_view(), name='systemimage-file'),
    path('<str:pk>/', SystemImagesAPIView.as_view()),
    path('<str:pk>/details', SystemImagesAPIView.as_view()),
    path('<str:pk>/update', SystemImagesAPIView.as_view()),
    path('', SystemImagesAPIView.as_view()),
]