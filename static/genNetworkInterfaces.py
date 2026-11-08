#!/usr/bin/env python3
""" Writes a booting node's network interface files.

mprov_boot_init.sh runs this on every boot of a diskless or stateful node.
It enrolls the boot with the mPCC when mprov_enroll is next to it (falling
back to the shared API key), reads the node's own system record and network
interfaces, and writes an ifcfg-<name> file for each interface plus
/etc/hostname. """


import socket
import yaml
import os
import sys
import time
import requests
from ipaddress import IPv4Network

# this boot's own credential (#381); mprov_boot_init.sh downloads it next to
# this script.  Without it (an older boot init), the shared API key is used.
try:
  import mprov_enroll
except ImportError:
  mprov_enroll = None


class mProvNetworkScriptGenerator():
  """ Reads this node's interfaces from the mPCC and writes their ifcfg files.
  Settings (mprovURL, apikey, ...) come from the global section of
  /etc/mprov/script-runner.yaml. """
  config_data = {}
  mprovURL = "http://127.0.0.1:8080/"
  apikey = ""
  # the mPCC's CA certificate, for an https mprovURL (the global caBundle setting).
  caBundle = ""
  heartbeatInterval = 10
  runonce = False
  sessionOk = False
  session = requests.Session()
  modules = ""
  netscriptDir = "/etc/sysconfig/network-scripts/"
  #netscriptDir = "/tmp"

  def __init__(self, **kwargs):
    """ Load the config and start an mPCC session, then fetch this system's
    record; exits if the mPCC can't be reached. """
    print("mProv Network Script Generator Starting.")

    # use the script-runner config
    self.configfile = "/etc/mprov/script-runner.yaml"
    
    # load our config
    self.load_config()

    if not self.netscriptDir.endswith("/"):
      self.netscriptDir += "/"
    # start a session
    if not self.startSession():
      print("Error: Unable to communicate with the mPCC.")
      sys.exit(1)
    self._getSelf()

  def yaml_include(self, loader, node):
    """ Ignore !include in the config: this script needs only the global section. """
    # disable includes, no need.
    return {}
    
  def load_config(self):
    """ Read /etc/mprov/script-runner.yaml and copy its global settings that this
    class knows onto it; exits if the file can't be read. """
    # load the config yaml
    # print(self.configfile)
    yaml.add_constructor("!include", self.yaml_include)
    
    if not(os.path.isfile(self.configfile) and os.access(self.configfile, os.R_OK)):
      print("Error: Unable to find a working config file, looking for /etc/mprov/script-runner.yaml")
      sys.exit(1)

    with open(self.configfile, "r") as yamlfile:
      self.config_data = yaml.load(yamlfile, Loader=yaml.FullLoader)

    # flatten the config space
    result = {}
    for entry in self.config_data:
      result.update(entry)
    self.config_data = result

    # map the global config on to our object
    for config_entry in self.config_data['global'].keys():
      try:
        getattr(self, config_entry)
        setattr(self, config_entry, self.config_data['global'][config_entry])
      except AttributeError:
        # ignore unused keys
        pass

    # exactly one trailing slash, so mprovURL + "systems/..." is always
    # a single slash however the config wrote it (#281).
    self.mprovURL = self.mprovURL.rstrip("/") + "/"

  def startSession(self):
    
    """ Set up the HTTP session: this boot's own certificate if it enrolls, else
    the shared API key.  True if the mPCC answers 200. """
    self.session.headers.update({
      'Authorization': 'Api-Key ' + self.apikey,
      'Content-Type': 'application/json'
      })
    if self.caBundle:
      self.session.verify = self.caBundle
    # enroll this boot and use its own certificate, over HTTPS (#381).
    if mprov_enroll is not None and mprov_enroll.enroll(self.session, self.mprovURL):
      self.mprovURL = mprov_enroll.use(self.session, self.mprovURL)

    # connect to the mPCC
    try:
      response = self.session.get(self.mprovURL, stream=True)
    except requests.exceptions.RequestException as e:
      # no response to report: the request itself failed (#280).
      print(f"Error: Communication error to the server. (Error: {e})", file=sys.stderr)
      self.sessionOk = False
      time.sleep(self.heartbeatInterval)
      return False
    self.sessionOk = True
    # get the sock from the session
    s = socket.fromfd(response.raw.fileno(), socket.AF_INET, socket.SOCK_STREAM)
    # get the address from the socket
    address = s.getsockname()
    self.ip_address=address
      
    # if we get a response.status_code == 200, we're ok.  If not,
    # our auth failed.
    return response.status_code == 200


  def _getSelf(self):
    """ Fetch this system (systems/?self) and its network interfaces into
    self.details; exits on any error. """
    # connect to the mPCC and get our information
    query = "systems/?self"
    response = self.session.get(self.mprovURL + query)
    if response.status_code == 200:
      try:
        self.details = response.json()[0]
      except Exception:
        print("Error: Unable to parse server response.")
        sys.exit(1)
      # got a valid record, grab the interfaces.
      response = self.session.get(f"{self.mprovURL}networkinterfaces/?system={self.details['id']}")
      if response.status_code == 200:
        try:
          self.details['networkinterfaces'] = response.json()
        except Exception:
          print("Error: Unable to parse server response.")
          sys.exit(1)
      else:
        print(f"Error: Unable to retrieve our network interfaces. Server returned {response.status_code}")
        sys.exit(1)
      return
    else:
      print(f"Error: Unable to get our system info from mPCC.  Server returned {response.status_code}")
      sys.exit(1)

  def generateNetworkInterfaceFiles(self):
    """ Write an ifcfg file for each of this system's interfaces, with its
    network's netmask and gateway (a gateway only on the interface marked as
    the gateway), and the hostname to /etc/hostname.  An interface with no
    network, or whose network can't be read, gets a /8 netmask and no gateway. """
    for intf in self.details['networkinterfaces']:
      if intf['network'] is None or intf['network'] == '':
        intf['gateway']=""
        intf['netmask']="255.0.0.0"
      else:
        # grab the network
        response = self.session.get(f"{self.mprovURL}networks/{intf['network']}/")
        if response.status_code == 200:
          netDetails = {}
          try:
            netDetails = response.json()
          except Exception as e:
            print(f"Warning: Unable to grab network information: Exception {e}")
            netDetails['gateway'] = ""
            netDetails['netmask'] = "255.0.0.0"
            netDetails['subnet'] = "10.0.0.0"
          intf['gateway']=netDetails['gateway']
          if netDetails['netmask'] is not None:
            intf['netmask'] = IPv4Network(f"{netDetails['subnet']}/{netDetails['netmask']}").netmask
            # intf['netmask']=netDetails['netmask']
          else:
            # same default as the other fallbacks (#282).
            intf['netmask'] = "255.0.0.0"
      
        else:
          print(f"Error: Unable to retrieve network information for network {intf['network']}. Server returned {response.status_code}")
          intf['gateway']=""
          intf['netmask']="255.0.0.0"
      with open(f"{self.netscriptDir}ifcfg-{intf['name']}",'+w') as netScript:
        netScript.write("# This file is generated by mProv. Changes WILL be overwritten\n")
        # this is a dirty, dirty, dirty, nasty, dirty hack...
        if intf['name'][:2] == 'ib':
          netScript.write("TYPE=InfiniBand\n")
        else:
          netScript.write("TYPE=Ethernet\n")
        
        netScript.write("BOOTPROTO=none\n")
        netScript.write(f"NAME={intf['name']}\n")
        netScript.write(f"DEVICE={intf['name']}\n")
        netScript.write(f"IPADDR={intf['ipaddress']}\n")
        netScript.write(f"NETMASK={intf['netmask']}\n")
        if intf['mac'] is not None and intf['mac'] != "":
          netScript.write(f"HWADDR={intf['mac']}\n")
        if intf['gateway'] is not None and intf['gateway'] != "" and intf['isgateway'] is True:
          netScript.write(f"GATEWAY={intf['gateway']}\n")
        # the IB stack sets the IPoIB MTU itself, so never write one for ib*.
        if intf['name'][:2] == 'ib':
          pass
        elif intf['mtu'] is not None and intf['mtu'] != "":
          netScript.write(f"MTU={intf['mtu']}\n")
        else:
          netScript.write("MTU=1500\n")
        netScript.write("ONBOOT=yes\n")
        netScript.write("NM_CONTROLLED=yes\n")
      
      with open("/etc/hostname","w") as hostfile:
        hostfile.write(self.details['hostname'])
      print(f"Name: {intf['name']}; MAC: {intf['mac']}; Gateway: {intf['gateway']}; IP: {intf['ipaddress']}; Netmask: {intf['netmask']}")

def main():
  """ Write this node's network interface files. """
  netGen = mProvNetworkScriptGenerator()
  netGen.generateNetworkInterfaceFiles()
if __name__ == "__main__":
    main()

