from django.conf import settings
from django.http import HttpResponse, HttpResponseNotAllowed
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
import markdown
from bs4 import BeautifulSoup

class MProvView( 
                generics.ListAPIView,
                mixins.CreateModelMixin, 
                mixins.RetrieveModelMixin,
                mixins.UpdateModelMixin,
                mixins.DestroyModelMixin,
                ):
    '''
# MProvView class

## Details
This class is used as a super class for all the views within the mProv Control Center.
It should be versatile enough to be used in just about any way as long as you set the
attributes right, setup a urls.py file right to pass 'pk' in for GET, PATCH, DELETE, POST, etc.
and make sure to add documentation to the class so that it can be displayed if anyone hits it.


    '''
    serializer_class = None
    queryset = None
    model = None
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name']
    #filter_backends = [DjangoFilterBackend]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    permission_classes = [HasAPIKey|IsAuthenticated]

    def __init__(self, **kwargs) -> None:
        if self.model is not None:
            self.queryset = self.model.objects.all()
        super().__init__(**kwargs)
    
    def checkContentType(self,request,*args, **kwargs):
        if(request.content_type != 'application/json'):
            if self.__doc__ == "" or self.__doc__ == None :
                message = "#" + self.__class__.__name__  + "\n\n"
                message += "Documentation pending. \n\n"
                message += "[Home](/)"
            else:
                message = "#" + self.__class__.__name__  + "\n\n"
                message += self.__doc__
                message += "\n\n[Home](/)"
            html = markdown.markdown(message)
            # let's dress up the HTML output a little.
            bs = BeautifulSoup("<html><head></head><body></body></html>", 'html.parser')
            body = bs.find('body')
            head_tag = bs.find('head')
            title_tag = bs.new_tag('title')
            title_tag.string = f"mProv Documentation - {self.__class__.__name__}"
            head_tag.insert_before(title_tag) 

            
            head_tag.append(BeautifulSoup('''
                <!-- Font Awesome Icons -->
                <link rel="stylesheet" href="/static/vendor/fontawesome-free/css/all.min.css">
                <!-- Bootstrap and adminLTE -->
                <link rel="stylesheet" href="/static/vendor/adminlte/css/adminlte.min.css" id="adminlte-css">
                <link rel="stylesheet" href="/static/vendor/bootswatch/minty/bootstrap.min.css" id="jazzmin-theme" />
                <!-- Custom fixes for django -->
                <link rel="stylesheet" href="/static/jazzmin/css/main.css">
                <link rel="stylesheet" href="/static/css/mprov.css">
            '''))
            body.append(BeautifulSoup(html))
            return HttpResponse(bs, content_type='text/html')
        return None

    def get(self, request, format=None, **kwargs):
        result = self.checkContentType(request, format=format)
        if result is not None:
            return result
        # if we are 'application/json' return an empty dict if
        # model is not set.
        if self.model == None:
            return Response(None)
        
        if 'pk' in kwargs:
            # someone is looking for a specific item.
            return self.retrieve(self, request, format=None, pk=kwargs['pk'])
        
        self.queryset = self.model.objects.all()

        # return the super call for get.
        return generics.ListAPIView.get(self, request, format=None);

    
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, args, kwargs)
    
    
    def put(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET","POST","PATCH","DELETE"])

    def patch(self, request, *args, **kwargs):
        if(type(request.user) == AnonymousUser ):
            request.user = User.objects.get(username='admin')
        return self.partial_update(request, args, kwargs)