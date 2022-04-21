"""mprov_control_center URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.views.generic import RedirectView
from django.urls import path, include
from .views import IndexAPIView
from systems.views import (
    SystemAPIView,
    SystemGroupAPIView,
    NetworkInterfaceAPIView,
)

from networks.views import (
    NetworkAPIView,
    NetworkTypeAPIView,
    SwitchAPIView,
    SwitchPortAPIView

)

from jobqueue.views import (
    JobServersAPIView,
    JobAPIView,
)


admin.site.site_header = 'mProv Control Center'
admin.site.site_title = 'mProv Control Center'
admin.site.index_title = 'mProv Control Center'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', IndexAPIView.as_view()),
    path('networks/', NetworkAPIView.as_view()),
    path('networktypes/', NetworkTypeAPIView.as_view()),
    
    path('systems/', SystemAPIView.as_view()),
    path('switches/', SwitchAPIView.as_view()),
    path('switchports/', SwitchPortAPIView.as_view()),
    path('systemgroups/', SystemGroupAPIView.as_view()),
    path('networkinterfaces/', NetworkInterfaceAPIView.as_view()),
    
    path('images/', include('systems.systemimage_urls')),
    path('distros/', include('osmanagement.distros_urls')),
    path('repos/', include('osmanagement.repos_urls')),
    path('jobmodules/', include('jobqueue.jobmodules_urls')),    
    path('jobservers/', include('jobqueue.jobservers_urls')),
    path('jobs/', include('jobqueue.jobs_urls'))

]
