from django.urls import path

from pki import views

urlpatterns = [
    path('jobserver/', views.EnrollJobServerView.as_view()),
    path('system/', views.EnrollSystemView.as_view()),
    path('renew/', views.RenewView.as_view()),
    path('recover/', views.RecoverView.as_view()),
    path('build/', views.BuildCredentialView.as_view()),
    path('ca.crt', views.ca_certificate),
]
