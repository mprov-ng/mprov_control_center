from django.urls import path
from scripts.views import FileDownloadView, ScriptAPIView

urlpatterns = [
    # files/<slug>/ comes first so the <str:pk>/ route below doesn't swallow it.
    path('files/<str:pk>/', FileDownloadView.as_view()),
    path('<str:pk>/', ScriptAPIView.as_view()),
    path('', ScriptAPIView.as_view()),
]