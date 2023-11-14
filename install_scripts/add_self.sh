#!/bin/bash

cat << EOF | /var/www/mprov_control_center/manage.py shell
from systems.models import System, NetworkInterface
from django.contrib.auth.models import User


import socket
import netifaces as ni

def get_ip_address(ifname):
  try:
    ip=str(ni.ifaddresses(ifname)[ni.AF_INET][0]['addr'])
    return ip

  except:
    return None

# get the admin user
user=User.objects.get(pk=1)

# get our interfaces.
if_list = socket.if_nameindex()

selfSys = System.objects.create(hostname=socket.gethostname(), created_by=user,updated='1970-01-01T00:00+00:00',timestamp='1970-01-01T00:00+00:00')
selfSys.save()

for intf in if_list:
  if intf[1] == "lo":
    continue
  intfip=get_ip_address(intf[1])
  netinf = NetworkInterface.objects.create(hostname=socket.gethostname(), name=intf[1], system=selfSys, ipaddress=intfip)
  netinf.save()

EOF
