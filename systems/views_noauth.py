
from .models import SystemImage, NetworkInterface
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.exceptions import NotFound
from common import render_config, flat_config
from common.views import MProvView
from systems.serializers import SystemImageSerializer, NetworkInterfaceDetailsSerializer
from rest_framework import generics
from django.http import HttpResponseNotAllowed, HttpResponse
from django.template import Template, Context
from django.shortcuts import render
import requests
import dns.resolver
from ipaddress import ip_address, ip_network
from osmanagement.models import OSDistro


def get_client_ip(request):
    """
    Identify the client by its actual socket peer address (REMOTE_ADDR).

    The X-Forwarded-For header is only honored when the connection
    provably arrives from a proxy listed in settings.TRUSTED_PROXIES
    (a list of exact IPs or CIDR networks).  In that case the forwarded
    chain is walked right to left -- every proxy appends the address of
    its own peer, so the rightmost entry is the one our trusted proxy
    just observed -- and the first address not in the trusted list is
    returned.  Forged headers from any other peer are ignored.
    """
    ip = request.META.get('REMOTE_ADDR')
    trusted = getattr(settings, 'TRUSTED_PROXIES', [])
    if not ip or not trusted:
        return ip
    try:
        networks = [ip_network(entry) for entry in trusted]
        peer = ip_address(ip)
    except ValueError:
        return ip
    if not any(peer in network for network in networks):
        return ip
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if not x_forwarded_for:
        return ip
    for candidate in reversed([entry.strip() for entry in x_forwarded_for.split(',')]):
        try:
            addr = ip_address(candidate)
        except ValueError:
            break
        if not any(addr in network for network in networks):
            return candidate
    return ip

class ImagesAPIView(MProvView, generics.ListAPIView):
    '''
# /images/

NOTE: This is a special API access point for retrieving system images, initramfs, and such.
This API expects keys to images.  If no primary key is specified, this documentation is
returned, or a JSON list of all images if the request content type is application/json.

## Accepted HTTP Methods:
- GET (with Primary Key, e.g. /images/compute/)
- GET (no primary key, e.g. /images/)


## Documentation

### GET (with primary key)
- Will redirect (302) to the image requested on the least loaded jobserver hosting it,
regardless of requested content type.  A primary key ending in .initramfs or .vmlinuz
redirects to that file, otherwise the .img is used.
- Jobservers registered by host name are skipped if the name doesn't resolve for the
client's address family.  Jobservers that fail to respond are skipped for the
current request only; this endpoint never modifies image-to-jobserver associations.
If no jobserver is left, a 404 is returned.

    '''
    model = SystemImage
    authentication_classes = [] #disables authentication
    permission_classes = [] #disables permission
    serializer_class = SystemImageSerializer
    
    def get(self, request, format=None, *args, **kwargs):

      isInitRamFS = False
      isKernel = False
      # grab the IP
      ip = get_client_ip(request)
      if 'pk' in kwargs:
        req = kwargs['pk'].split('.', 1)
        imgName = req[0]
        if len(req) > 1:
          # getting an extension
          if(req[1] == "initramfs"):
            # this is an initramfs query.
            isInitRamFS=True
            isKernel=False
          if(req[1] == "vmlinuz"):
            isKernel=True
            isInitRamFS=False

        image = SystemImage.objects.filter(pk=imgName).first()
        if image is None:
          raise NotFound(detail="No such image.", code=404)
      else: 
        # no pk in image, spit out a list then.
        result = self.checkContentType(request, format=format, kwargs=kwargs)
        if result is not None:
            return result  
        # no pk in image, spit out a list then.
        self.queryset = SystemImage.objects.all()
        return(generics.ListAPIView.get(self, request, format=None)) 
      # choose a jobserver with the lowest one minute load avg.
      js_set = self.getJobserver(image, ip)
      js = None
      js = js_set[0]
      # if ":" in js.address:
      #   js.address = f"[{js.address}]"
      imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug
      if isInitRamFS:
        imageURL += ".initramfs"
      else:
        if isKernel:
          imageURL += ".vmlinuz"
        else:
          imageURL += ".img"  
      try: 
        response = requests.head(imageURL,timeout=1)
        statCode = response.status_code
      except Exception as e:
        print(f"Error occurred while fetching image: {e}")
        statCode = 0
      while ( statCode <= 199 or statCode >=400):
        # jobserver gave a bad response; skip it for this request only.
        # An unauthenticated GET must never persist jobserver-to-image
        # association changes: one momentary fetch failure would otherwise
        # permanently strip the jobserver from the image (#321).
        print("Skipping Jobserver " + str(js) + ", URL: " + imageURL + " not accessible. Status: " + str(statCode))
        js_set = [candidate for candidate in js_set if candidate.pk != js.pk]
        if len(js_set) == 0:
          raise NotFound(detail="Error 404, No responsive Jobservers for Image", code=404)
        js = js_set[0]
        # if ":" in js.name:
        #   js.address = f"[{js.address}]"
        imageURL = "http://" + js.address + ":" + str(js.port) + "/images/" + image.slug + "/" + image.slug
        if isInitRamFS:
          imageURL += ".initramfs"
        else:
          if isKernel:
            imageURL += ".vmlinuz"
          else:
            imageURL += ".img"  
        try: 
          response = requests.head(imageURL,timeout=1)
          statCode = response.status_code
        except requests.RequestException:
          statCode=0
      print(f"Redirecting client to: {imageURL}")
      return redirect(imageURL)        

    def getJobserver(self, image, clientIP=None):
      """
      Returns the image's job servers, lowest one minute load avg. first,
      leaving out any whose name doesn't resolve for the client's address
      family (AAAA for an IPv6 client).  Job servers registered by IP
      address are always kept.  Raises NotFound if none are left.
      """

      js_set = list(image.jobservers.all().order_by('one_minute_load'),)
      if(len(js_set)==0):
        # if there are no jobservers, return 404
        raise NotFound(detail="Error 404, No Jobservers in mPCC for Image", code=404)
      if clientIP is None:
        return js_set

      rdtype = "AAAA" if ":" in clientIP else "A"
      resolvable = []
      errors = []
      for js in js_set:
        try:
          ip_address(js.address)
          # a valid IP needs no lookup.
          resolvable.append(js)
          continue
        except ValueError:
          # if not a valid ip, assume it's a host name
          pass
        try:
          # only checks that the name resolves.
          dns.resolver.resolve(str(js.address), rdtype, search=True)
        except Exception as e:
          errors.append(f"{js}: {e}")
          continue
        resolvable.append(js)
      if len(resolvable) == 0:
        family = "IPv6 " if rdtype == "AAAA" else ""
        raise NotFound(detail=f"Error 404, No resolvable {family}Jobservers for Image: {'; '.join(errors)}", code=404)
      print("Jobserver: " + str(resolvable[0]))
      return resolvable

    def post(self, request, *args, **kwargs):
      return HttpResponseNotAllowed(["GET"])

    def delete(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

    def put(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

    def patch(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])

class IPXEAPIView(MProvView):
    model = NetworkInterface
    serializer_class = NetworkInterfaceDetailsSerializer
    authentication_classes = [] #disables authentication
    permission_classes = [] #disables permission
    def get(self, request, format=None, **kwargs):
        # result = self.checkContentType(request, format=format, kwargs=kwargs)
        # if result is not None:
        #     return result
        # grab the IP
        ip = get_client_ip(request)
        #ip="172.16.10.1"
        # now try to grab the nic for this IP
        queryset = self.model.objects.all()
        queryset = queryset.filter(ipaddress=ip)
        qscnt = queryset.count()
        # our IP is not found, let's fall back to the NADS image.
        if qscnt == 0:
            try:
                imgQs = SystemImage.objects.get(name='__nads__')
            except SystemImage.DoesNotExist:
                print("Error: You are missing a system image of the name '__nads__' so autodetection will fail.")
                raise NotFound(detail="No __nads__ image.", code=404) from None
            if type(imgQs) is SystemImage:  
                # there is a __nads__ image, let's serve that.
                # spoof a NIC object
                class Obj:
                    pass
                system=Obj()
                system.systemimage = imgQs
                # setattr(system, 'systemima?ge', imgQs)
                nic = Obj()
                nic.system = system
                nic.bootable = False
                system.provision = False
                # setattr(nic, 'system', system)

                nics = [ nic ]
                queryset = nics
        else:
          # here we should have a system

          # the kernel cmdline is rendered as a template further below, allowing recursive templating.
          if qscnt > 1:
            print(f"WARN: More than 1 NIC for IP {ip}.  Using the first bootable one.")
          
          # first let's find a bootable nic if one exists.
          nic=None
          for s_nic in queryset:
             if s_nic.bootable:
                nic = s_nic
                break
          if nic is None:
            # no bootable nic, so hand the template the first one and let it
            # fall through to the local boot branch.
            context= {
              'nic': queryset.first(),
            }
            return(render(template_name="ipxe", request=request, context=context, content_type="text/plain" ))
            
             
          if nic.system.systemimage is None:
            print("Error: System has no image assigned, netbooting not possible.")
            raise NotFound(detail="Error: System has no image assigned, netbooting not possible.", code=404)
        nic.bootserver=f"{request.scheme}://{request.META.get('SERVER_NAME')}:{request.META.get('SERVER_PORT')}"
        
        # if "." in nic.bootserver:
        #   # remove the domain if one exists
        #   nic.bootserver, _ = nic.bootserver.split(".", 1)
        rescue_param = " mprov_rescue=0"
        if "rescue" in request.query_params:
            rescue_param = " mprov_rescue=1"
            
        class GenericObject:
          pass    
        if not hasattr(nic.system.systemimage.osdistro, "install_kernel_cmdline"):
           # no distro on the image, so use a blank one to get the defaults.
           nic.system.systemimage.osdistro = OSDistro()

        # check for the __nads__ image, which means a N.A.D.S. boot.
        is_nads = nic.system.systemimage.name == "__nads__"

        # the boot options, merged from the distro, system groups, image and
        # system (see common.render_config).  A N.A.D.S. boot has no system, so
        # it gets the image's merge.
        if is_nads:
          config = flat_config(render_config(nic.system.systemimage))
        else:
          config = nic.system.config
        boot = {
          'install_kernel_cmdline': config.get('install_kernel_cmdline', ''),
          'initial_mods': config.get('initial_mods', ''),
          'tmpfs_root_size': config.get('tmpfs_root_size', 0),
        }
        template = Template(boot['install_kernel_cmdline'])
        context = Context(dict(nic=nic, boot=boot))

        if is_nads:
          # set the mac to the provisioning interface.
          nic.mac = nic.system.systemimage.osdistro.prov_interface
        # not set to provision, we just return and let the template handle it.
        # A N.A.D.S. boot always netboots, so it carries on to get the
        # templated cmdline, the rescue parameter and any custom iPXE script.
        if not nic.system.provision and not is_nads:
          context= {
            'nic': nic,
          }
          return(render(template_name="ipxe", request=request, context=context, content_type="text/plain" ))



        

        if not nic.system.systemimage.customIPXE == "" and nic.system.systemimage.customIPXE is not None:
           # let's just serve up the custom IPXE script.
           template = Template(nic.system.systemimage.customIPXE)
           context = Context(dict(nic=nic, boot=boot))
           rendered: str = template.render(context)
           return HttpResponse(content=rendered)
        
        rendered: str = template.render(context)
        boot['install_kernel_cmdline'] = rendered + rescue_param
        print("PXE Request from: " + ip)
        context= {
          'nic': nic,
          'boot': boot,
        }
        return(render(template_name="ipxe", request=request, context=context, content_type="text/plain" ))
