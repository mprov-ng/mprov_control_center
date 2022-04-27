from django.conf import settings
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_api_key.permissions import HasAPIKey
from rest_framework.views import APIView
from rest_framework import mixins, generics
from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.contrib.auth.models import AnonymousUser, User


class MProvView( 
                generics.ListAPIView,
                mixins.CreateModelMixin, 
                #generics.GenericAPIView,
                mixins.DestroyModelMixin,
                mixins.UpdateModelMixin,
                ):
    
    template = "docs.html"
    serializer_class = None
    queryset = None
    model = None
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name']
    #filter_backends = [DjangoFilterBackend]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    permission_classes = [HasAPIKey|IsAuthenticated]
    

    def get(self, request, format=None):
        if(request.content_type != 'application/json'):
            return render(request, self.template, {})
        # if we are 'application/json' return an empty dict if
        # model is not set.
        if self.model == None:
            return Response(None)
        
        self.queryset = self.model.objects.all()

        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);

    
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, args, kwargs)
    
    def put(self, request, *args, **kwargs):
        return self.update(request, args, kwargs)

    def patch(self, request, *args, **kwargs):
        if(type(request.user) == AnonymousUser ):
            request.user = User.objects.get(username='admin')
        return self.partial_update(request, args, kwargs)