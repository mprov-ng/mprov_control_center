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
from django.urls import path, include, re_path
from .views import DataTypeView, IndexAPIView
from systems.views import (
    SystemAPIView,
    SystemBMCAPIView,
    SystemGroupAPIView,
    NetworkInterfaceAPIView,
    SystemRegAPIView,
)
from systems.views_noauth import IPXEAPIView


from networks.views import (
    NetworkAPIView,
    NetworkTypeAPIView,
    SwitchAPIView,
    SwitchPortAPIView

)

from osmanagement.views_noath import OSRepoURLAPIView

from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = 'mProv Control Center'
admin.site.site_title = 'mProv Control Center'
admin.site.index_title = 'mProv Control Center'

urlpatterns = [
    path('accounts/profile/', RedirectView.as_view(url='/admin/')),
    path('admin/', admin.site.urls),
    path('', IndexAPIView.as_view()),
    path('networks/', NetworkAPIView.as_view()),
    path('networks/<str:pk>/', NetworkAPIView.as_view()),
    
    path('networktypes/', NetworkTypeAPIView.as_view()),
    path('networktypes/<str:pk>/', NetworkTypeAPIView.as_view()),

    path('systems/register', SystemRegAPIView.as_view()),
    
    path('systems/', SystemAPIView.as_view()),
    path('systems/<str:pk>/', SystemAPIView.as_view()),
    
    path('systembmcs/', SystemBMCAPIView.as_view()),
    path('systembmcs/<str:pk>/', SystemBMCAPIView.as_view()),

    path('switches/', SwitchAPIView.as_view()),
    path('switches/<str:pk>/', SwitchAPIView.as_view()),
    
    path('switchports/', SwitchPortAPIView.as_view()),
    path('switchports/<str:pk>/', SwitchPortAPIView.as_view()),
    
    path('systemgroups/', SystemGroupAPIView.as_view()),
    path('systemgroups/<str:pk>/', SystemGroupAPIView.as_view()),
    
    path('networkinterfaces/', NetworkInterfaceAPIView.as_view()),
    path('networkinterfaces/<str:pk>/', NetworkInterfaceAPIView.as_view()),

    path('ipxe/', IPXEAPIView.as_view()),
    
    path('images/', include('systems.images_urls')),
    path('systemimages/', include('systems.systemimage_urls')),
    path('distros/', include('osmanagement.distros_urls')),
    path('repos/', include('osmanagement.repos_urls')),
    path('ostypes/', include('osmanagement.ostypes_urls')),
    path('jobmodules/', include('jobqueue.jobmodules_urls')),    
    path('jobservers/', include('jobqueue.jobservers_urls')),
    path('jobs/', include('jobqueue.jobs_urls')),
    path('scripts/', include('scripts.scripts_urls')),
    path('kernels/', include('systems.kernels_urls')),

    path('osrepos/', include('osmanagement.osrepos_urls')),

    path('datamodel/', DataTypeView.as_view()),
    
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    
] 
