#!/usr/bin/pyton3.8


import json
import socket
import uuid
import yaml, os, sys, glob, time
import traceback
import requests
import sh
from ipaddress import IPv4Network



def exception_hook(exctype, value, tracebak):
  traceback.print_exc()
  print("\n\nERROR: Installer failed.  Dropping to shell.  Note: You are still in the RAM disk.")
  os.execv("/bin/setsid" "/bin/bash -m  <> /dev/tty1 >&0 2>&1")


class mProvNetworkScriptGenerator():
  config_data = {}
  mprovURL = "http://127.0.0.1:8080/"
  apikey = ""
  heartbeatInterval = 10
  runonce = False
  sessionOk = False
  session = requests.Session()
  modules = ""
  netscriptDir = "/etc/sysconfig/network-scripts/"
  #netscriptDir = "/tmp"

  def __init__(self, **kwargs):
    print("mProv Network Script Generator Starting.")

    # use the jobserver config
    self.configfile = "/etc/mprov/script-runner.yaml"
    
    # load our config
    self.load_config()

    if self.netscriptDir[:-1] != "/":
      self.netscriptDir += "/"
    # start a session
    if not self.startSession():
      print("Error: Unable to communicate with the mPCC.")
      sys.exit(1)
    self._getSelf()

  def yaml_include(self, loader, node):
    # disable includes, no need.
    return {}
    
  def load_config(self):
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
      except:
        # ignore unused keys
        pass
    pass

  def startSession(self):
    
    self.session.headers.update({
      'Authorization': 'Api-Key ' + self.apikey,
      'Content-Type': 'application/json'
      })

    # connect to the mPCC
    try:
      response = self.session.get(self.mprovURL, stream=True)
    except:
      print("Error: Communication error to the server.  Retrying.", file=sys.stderr)
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
    # connect to the mPCC and get our information
    query = "systems/?self"
    response = self.session.get(self.mprovURL + query)
    if response.status_code == 200:
      try:
        self.details = response.json()[0]
      except:
        print("Error: Unable to parse server response.")
        sys.exit(1)
      # got a valid record, grab the interfaces.
      response = self.session.get(f"{self.mprovURL}/networkinterfaces/?system={self.details['id']}")
      if response.status_code == 200:
        try:
          self.details['networkinterfaces'] = response.json()
        except:
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
    for intf in self.details['networkinterfaces']:
      if intf['network'] is None or intf['network'] == '':
        intf['gateway']=""
        intf['netmask']="255.0.0.0"
      else:
        # grab the network
        response = self.session.get(f"{self.mprovURL}/networks/{intf['network']}/")
        if response.status_code == 200:
          netDetails = {}
          try:
            netDetails = response.json()
          except Exception as e:
            print(f"Warning: Unable to grab network information: Exception {e}")
            netDetails['gateway'] = ""
            netDetails['netmask'] = "255.0.0.0"
            netDetails['subnet'] = "10.0.0.0"
            pass
          intf['gateway']=netDetails['gateway']
          if netDetails['netmask'] is not None:
            intf['netmask'] = IPv4Network(f"{netDetails['subnet']}/{netDetails['netmask']}").netmask
            # intf['netmask']=netDetails['netmask']
      
        else:
          print(f"Error: Unable to retrieve network information for network {intf['network']}. Server returned {response.status_code}")
          intf['gateway']=""
          intf['netmask']="255.0.0.0"
      with open(f"{self.netscriptDir}ifcfg-{intf['name']}",'+w') as netScript:
        netScript.write("# This file is generated by mProv. Changes WILL be overwritten\n")
        netScript.write(f"TYPE=Ethernet\n")
        netScript.write(f"BOOTPROTO=none\n")
        netScript.write(f"NAME={intf['name']}\n")
        netScript.write(f"DEVICE={intf['name']}\n")
        netScript.write(f"IPADDR={intf['ipaddress']}\n")
        netScript.write(f"NETMASK={intf['netmask']}\n")
        if intf['mac'] is not None and intf['mac'] != "":
          netScript.write(f"HWADDR={intf['mac']}\n")
        if intf['gateway'] is not None and intf['gateway'] != "" and intf['isgateway'] == True:
          netScript.write(f"GATEWAY={intf['gateway']}\n")
        if intf['mtu'] is not None and intf['mtu'] != "":
          netScript.write(f"MTU={intf['mtu']}\n")
        else:
          netScript.write(f"MTU=1500\n")
        netScript.write(f"ONBOOT=yes\n")
        netScript.write(f"NM_CONTROLLED=yes\n")
      
      with open(f"/etc/hostname","w") as hostfile:
        hostfile.write(self.details['hostname'])
      print(f"Name: {intf['name']}; MAC: {intf['mac']}; Gateway: {intf['gateway']};  IP: {intf['ipaddress']};, Netmask:{intf['netmask']}")

    pass
def main():
  netGen = mProvNetworkScriptGenerator()
  netGen.generateNetworkInterfaceFiles()
def __main__():
    main()
if __name__ == "__main__":
    main()

