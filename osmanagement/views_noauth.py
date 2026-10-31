from .models import OSRepo
from common.views import MProvView
from rest_framework import generics
from .serializers import OSRepoAPISerializer
from rest_framework.exceptions import NotFound
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.utils.html import format_html
from bs4 import BeautifulSoup
from systems.views_noauth import get_client_ip
from jobqueue.models import route_order


class OSRepoURLAPIView(MProvView, generics.ListAPIView):
      '''
# /osrepos/

Public, unauthenticated access to the OS repositories in the mPCC.

## Accepted HTTP Methods:
- GET (no parameters)
- GET (with Primary Key, ie: /osrepos/1/)
- GET (with Primary Key and a path, ie: /osrepos/1/repodata/repomd.xml)

## Documentation

### GET method (no parameters)
Returns the list of repositories.  Managed repositories link to /osrepos/&lt;id&gt;/,
unmanaged ones link to their package URL.

### GET method (with primary key)
Redirects (302) to a responsive job server that hosts the repository: one with
an address on the client's network first, then the least loaded, ties at random
(#254).  Any path after the primary key is appended to the redirect.  Returns
404 if no responsive job server hosts the repository.
      '''
      model = OSRepo
      authentication_classes = [] #disables authentication
      permission_classes = [] #disables permission
      serializer_class = OSRepoAPISerializer
    
      def get(self, request, format=None, *args, **kwargs):
        # result = self.checkContentType(request, format=format, kwargs=kwargs)
        # if result is not None:
        #     return result
        if 'pk' in kwargs:
          repo = OSRepo.objects.filter(pk=kwargs['pk']).first()
          if repo is None:
            raise NotFound(detail="No such repository.", code=404)
        else: 
          result = self.checkContentType(request, format=format, kwargs=kwargs)
          # no pk in the request, spit out a list then.
          self.queryset = OSRepo.objects.all()
          if result is not None:
              
              # let's dress up the HTML output a little.
              output_html = result.content.decode(result.charset)

              bs = BeautifulSoup(output_html, features="html.parser")
              body = bs.find('body')
              html="<br /><br /><h2>Repository List</h2><br /><ul>"
              for repo in list(self.queryset):
                if repo.managed:
                  html+=format_html("<li><a href='/osrepos/{}/'>{}</a><br></li>", repo.id, repo.name)
                else:
                  html+=format_html("<li><a href='{}'>{}</a><br></li>", repo.repo_package_url, repo.name)
              html+="</ul>"
              body.append(BeautifulSoup(html, features="html.parser"))
              result.content = str(bs).encode(result.charset)
              return result 
          # no pk in the request, spit out a list then.
          return(generics.ListAPIView.get(self, request, format=None))
        if not repo.hosted_by.exists():
          # if there are no jobservers, return 404
          raise NotFound(detail="No job servers host this repository.", code=404)
        # a responsive job server on the client's network, least loaded
        # first (#254); unresponsive ones are kept on the repo but not
        # routed to.
        js_set = route_order(repo.hosted_by.all(), get_client_ip(request))
        if(len(js_set)==0):
          raise NotFound(detail="No responsive job servers host this repository.", code=404)
        js = js_set[0]
        # the address it registered on the client's network, if any (mprov_jobserver#114).
        host = js.route_address
        if ":" in host and not host.startswith("["):
          host = f"[{host}]"
        if 'redirect_url' in kwargs:
          rurl = kwargs['redirect_url']
        else:
          rurl = ""
        repoURL = f"http://{host}:{str(js.port)}/repos/{repo.id}/{rurl}"

        return redirect(repoURL)        
      def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

      def delete(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def put(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])

      def patch(self, request, *args, **kwargs):
          return HttpResponseNotAllowed(["GET"])
