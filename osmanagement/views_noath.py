from .models import OSRepo
from common import MProvView
from rest_framework import generics
from .serializers import OSRepoAPISerializer
from rest_framework.exceptions import NotFound
import random
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from bs4 import BeautifulSoup


class OSRepoURLAPIView(MProvView, generics.ListAPIView):
      model = OSRepo
      # TODO: placeholder for now to test 302 redirects
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      serializer_class = OSRepoAPISerializer
    
      def get(self, request, format=None, *args, **kwargs):
        # result = self.checkContentType(request, format=format, kwargs=kwargs)
        # if result is not None:
        #     return result
        if 'pk' in kwargs:
          repo = OSRepo.objects.get(pk=kwargs['pk'])
        else: 
          result = self.checkContentType(request, format=format, kwargs=kwargs)
          # no pk in image, spit out a list then.
          self.queryset = OSRepo.objects.all()
          if result is not None:
              
              # let's dress up the HTML output a little.
              output_html = result.content.decode(result.charset)

              bs = BeautifulSoup(output_html, features="html.parser")
              body = bs.find('body')
              html="<br /><br /><h2>Repository List</h2><br /><ul>"
              for repo in list(self.queryset):
                if repo.managed:
                  html+=f"<li><a href='/osrepos/{repo.id}/'>{repo.name}</a><br></li>"
                else:
                  html+=f"<li><a href='{repo.repo_package_url}'>{repo.name}</a><br></li>"
              html+=f"</ul>"
              body.append(BeautifulSoup(html, features="html.parser"))
              result.content = str(bs).encode(result.charset)
              return result 
          # no pk in image, spit out a list then.
          return(generics.ListAPIView.get(self, request, format=None))
        # choose a random jobserver
        js_set = list(repo.hosted_by.all())
        js = None
        if(len(js_set)==0):
          # if there are no jobservers, return 404
          raise NotFound(detail="Error 404, No Jobservers for Repo", code=404) 
        print(js_set)
        js = random.choice(js_set)
        if 'redirect_url' in kwargs:
          rurl = kwargs['redirect_url']
        else:
          rurl = ""
        imageURL = f"http://{js.address}:{str(js.port)}/repos/{repo.id}/{rurl}"

        return redirect(imageURL)        
      def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

      def delete(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def put(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def patch(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])
