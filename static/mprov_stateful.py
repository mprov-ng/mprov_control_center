#!/usr/bin/python3

import socket
import uuid
import yaml, os, sys, glob, time
import parted
import traceback
import requests
import sh

# This scirpt will:
# - grab the disklayout from the mPCC, 
# - build the partition table(s)
# - build the file system(s)
# - update the /etc/fstab
# - mount the root filesystem to a subdir
# - chroot in and mount the remaining filesystems, 
# - rsync the RAM image to the disk
# - mark the system's bootable NIC as not bootable to indicate it's provisioned
# - hand control over to systemd or reboot

def exception_hook(exctype, value, tracebak):
  traceback.print_exc()
  print("\n\nERROR: Installer failed.  Dropping to shell.  Note: You are still in the RAM disk.")
  os.execv("/bin/setsid" "/bin/bash -m  <> /dev/tty1 >&0 2>&1")


class mProvStatefulInstaller():
  config_data = {}
  mprovURL = "http://127.0.0.1:8080/"
  apikey = ""
  heartbeatInterval = 10
  runonce = False
  sessionOk = False
  disklayout = {}
  session = requests.Session()
  ip_address = None

  def __init__(self, **kwargs):
    print("mProv Stateful Installer Starting.")

    # use the jobserver config
    self.configfile = "/etc/mprov/jobserver.yaml"
    
    # load our config
    self.load_config()

    # start a session
    if not self.startSession():
      print("Error: Unable to communicate with the mPCC.")
      sys.exit(1)

  def yaml_include(self, loader, node):
    # disable includes, no need.
    return {}
    #   # Get the path out of the yaml file
    # file_name = os.path.join(os.path.dirname(loader.name), node.value)
    
    # # we have a glob, so we will iterate.
    # result = {}
    # for file in glob.glob(file_name):
    #   with open(file) as inputfile:
    #     result.update(yaml.load(inputfile, Loader=yaml.FullLoader)[0])
    # return result

  def load_config(self):
    # load the config yaml
    # print(self.configfile)
    yaml.add_constructor("!include", self.yaml_include)
    
    if not(os.path.isfile(self.configfile) and os.access(self.configfile, os.R_OK)):
      print("Error: Unable to find a working config file.")
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

  def buildDisks(self):
    self._getDiskLayout()
    disks = "" 
    for disk in self.disklayout:
      disks += f"{disk['diskname']},"
    print("THIS OPERATION WILL DESTROY THE CONTENTS OF THE FOLLOWING DISKS: ")
    print(f"\t{disks}")
    print("CTRL-C NOW TO STOP IT!")
    time.sleep(5)
    print("Building partitions and filesystems...")
    # stop all arrays
    sh.mdadm(['--stop', '--scan'])
    try:
      os.unlink("/tmp/fstab")
    except:
      pass
    partnum=1
    # TODO: support for extended partitions
    # TODO: if the next part number is == 4 then create an extended partition 
    # TODO: and put the new part in there, for extended parts
    for pdisk in self.disklayout:
      # don't do raid disks here.
      if pdisk['dtype'] == 'mdrd':
        continue
      device = parted.getDevice(pdisk['diskname'])
      disk = parted.freshDisk(device, 'gpt' )
      start=1
      sectorsize=device.sectorSize
      fillpart = None
      pdisk['partitions'] = sorted(pdisk['partitions'], key=lambda d: d['partnum'])
      for part in pdisk['partitions']:
        # if this is the fill partition, make note of that and skip for now.
        if part['fill']:
          fillpart=part
          continue
        
        start = start + self._createPartition(device, disk, part, sectorsize, start) + 1
        if part['filesystem'] != 'raid' and part['mount'] != 'raid':
          partuuid = self._makeFS(part, pdisk)


          # update /tmp/fstab
          with open("/tmp/fstab", "a") as fstab:
            fstab.write(f"UUID={partuuid}\t{part['mount']}\t\t{part['filesystem']}\tdefaults\t0 0\n")

        partnum+=1

      if fillpart is not None:
        self._createPartition(device, disk, fillpart, sectorsize, start)    
        
        if part['filesystem'] != 'raid' and part['mount'] != 'raid':
          partuuid = self._makeFS(fillpart, pdisk)
          # update /tmp/fstab
          with open("/tmp/fstab", "a") as fstab:
            fstab.write(f"UUID={partuuid}\t{fillpart['mount']}\t\t{fillpart['filesystem']}\tdefaults\t0 0\n")
    
  def buildRAIDs(self):
    print("Building software RAID devices ... ")
    for pdisk in self.disklayout:
      # don't do raid disks here.
      if pdisk['dtype'] != 'mdrd':
        continue
      #  mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/hd[ac]1
      mdadm_cmd = f"--create {pdisk['diskname']} --metadata=0.90 --force --level={pdisk['raidlevel']} --raid-devices={len(pdisk['members'])} "
      for member in pdisk['members']:
        dev = member['disklayout']['diskname']
        member_part = f"{dev}{member['partnum']}"
        mdadm_cmd += f"{member_part} "
        # zero the superblock
        sh.mdadm(['--zero-superblock', f"{member_part}"])
        sh.wipefs(['--all', '--force', f"{member_part}"])
      # convert mdadm_cmd to something the sh mod can use
      sh.mdadm(mdadm_cmd.split())
      # spoof a partition to _makeFS()
      part = {
        'filesystem': pdisk['filesystem'],
        'partnum':'',
      }
      partuuid = self._makeFS(part, pdisk)
      # update /tmp/fstab
      with open("/tmp/fstab", "a") as fstab:
        fstab.write(f"UUID={partuuid}\t{pdisk['mount']}\t\t{pdisk['filesystem']}\tdefaults\t0 0\n")
    

  def mountDisks(self):
    # TODO: step through /tmp/fstab and mount the filesystems into /newroot/
    os.makedirs("/newroot", exist_ok=True)
    with open("/tmp/fstab", "r") as file:
      while (line := file.readline().rstrip()):
        print(line)

        fstab_entry = line.split()
        os.makedirs(f"/newroot{fstab_entry[1]}", exist_ok=True)
        if fstab_entry[1] != "none":
          sh.mount(
            [
              fstab_entry[0],
              f"/newroot{fstab_entry[1]}"
            ]
          )

  def copyRoot(self):
    # TODO: rsync everything and copy /tmp/fstab to /newroot/etc/fstab
    sh.rsync([
      "-arx",
      "/",
      "/newroot"
    ])
    sh.cp(["/tmp/fstab", "/newroot/etc/fstab"])
    pass

  def switchRoot(self):
    pass

  def to_mebibytes(self, value):
    return value / (2 ** 20)

  def to_megabytes(self, value):
    return value / (10 ** 6)

  def from_mebibytes(self, value, sectorsize):
    return int((value * (2 ** 20))/sectorsize)

  def _getDiskLayout(self):
    # connect to the mPCC and get our information
    query = "systems/?self"
    response = self.session.get(self.mprovURL + query)
    if response.status_code == 200:
      try:
        systemDetails = response.json()[0]
      except:
        print("Error: Unable to parse server response.")
        sys.exit(1)
      self.disklayout = systemDetails['disklayouts']
      return
    else:
      print(f"Error: Unable to get disk info from mPCC.  Server returned {response.status_code}")
      sys.exit(1)

  def _createPartition(self, device, disk, part, sectorsize, start):
    geometry = parted.Geometry(
      device=device,
      start=start,
      length=self.from_mebibytes(part['size'],sectorsize)
    )
    if part['filesystem'] == 'linux-swap':
      part['filesystem'] = 'linux-swap(v1)'
    if part['filesystem'] != 'raid':
      fs = parted.FileSystem(
        type=part['filesystem'], 
        geometry=geometry,
      )
    else:
      part['filesystem'] = None
      fs=None


    partition = parted.Partition(
      disk=disk,
      type=parted.PARTITION_NORMAL,
      fs=fs,
      geometry=geometry
    )
    disk.addPartition(partition=partition, constraint=device.optimalAlignedConstraint)
    
    disk.commit()
    return self.from_mebibytes(part['size'], sectorsize)
    

  def _makeFS(self, part, pdisk):
    # make a uuid 
    partuuid = uuid.uuid4()
    if part['filesystem'] == 'xfs':
      part['uuid'] = f"uuid={partuuid}"
      part['uuidopt'] = "-m"
      part['force'] = "-f"
    else:
      part['uuidopt'] = "-U"
      part['uuid'] = f"{partuuid}"
      part['force'] = "-F"

    # make the filesystem
    if part['filesystem'] == 'linux-swap(v1)':
      # print("mkswap ",f"{pdisk['diskname']}{part['partnum']}",f"{part['uuidopt']}",  f"{part['uuid']}")
      sh.mkswap(f"{pdisk['diskname']}{part['partnum']}",f"{part['uuidopt']}",  f"{part['uuid']}")
      part['mount'] = "none"
      # put this back
      part['filesystem'] = "swap"
      
    else:
      sh.mkfs(f"{part['force']}", f"-t", f"{part['filesystem']}", f"{part['uuidopt']}", f"{part['uuid']}", f"{pdisk['diskname']}{part['partnum']}")
    return partuuid

def main():
  sInstaller = mProvStatefulInstaller()
  sInstaller.buildDisks()
  sInstaller.buildRAIDs()
  sInstaller.mountDisks()
  sInstaller.copyRoot()
  sInstaller.switchRoot()
  pass

def __main__():
    main()
    raise Exception("Installer Exitted without switch_root()")
if __name__ == "__main__":
    main()
