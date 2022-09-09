#!/usr/bin/python3

import json
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
  bootdisk = None
  bootpart = None

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

    # disks with boot partitions.
    # This is an array because more than
    # one disk can have a bootable partition.
    # we will probably error  if more than one is detected.
    # as figuring out what disk the user WANTS to boot from
    # requires psychic powers that Python simply can't handle
    bootdisks = []
    for disk in self.disklayout:
      disks += f"{disk['diskname']},"
      # look for boot partitions
      for part in disk['partitions'] :
        if part['bootable'] :
          bootdisks.append(disk['diskname'])

    if len(bootdisks) > 1: 
      print("ERROR: More than one disk is set to boot, but I can't tell which one really IS the boot disk.")
      sys.exit(1)

    if len(bootdisks) < 1:
      print("ERROR: You don't seem to have set a boot partition in your config. ")
      sys.exit(1)

    if len(bootdisks) == 1 :
      self.bootdisk = bootdisks[0]
      
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

    for pdisk in self.disklayout:
      # don't do raid disks here.
      if pdisk['dtype'] == 'mdrd':
        continue
      device = parted.getDevice(pdisk['diskname'])
      disk = parted.freshDisk(device, 'gpt' )
      
      sectorsize=device.sectorSize
      start=self.from_mebibytes(1, sectorsize)
      fillpart = None
      
      if pdisk['diskname'] == self.bootdisk:

        # clear the PMBR Boot flag from the disk
        disk.unsetFlag(parted.DISK_GPT_PMBR_BOOT)

        # if we are a boot disk, let's make a couple of needed parttitions
        # create a biosboot partition
        bootpart={'filesystem': 'biosboot', 'size': 1, 'fill': False, 'partnum': 1}
        start = start + self._createPartition(device, disk, bootpart, sectorsize, start, parttype=parted.PARTITION_NORMAL)
        partnum += 1

        # create an EFI partition
        bootpart={'filesystem': 'efi', 'size': 100, 'fill': False, 'partnum': 2}
        start = start + self._createPartition(device, disk, bootpart, sectorsize, start, parttype=parted.PARTITION_NORMAL)
        self._makeFS(bootpart, pdisk)
        partnum += 1

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
      mdadm_cmd = f"--create {pdisk['diskname']} -R --force --level={pdisk['raidlevel']} --raid-devices={len(pdisk['members'])} "
      for member in pdisk['members']:
        dev = member['disklayout']['diskname']
        partOffset = 0
        if dev == self.bootdisk:
          # boot disk, we are going to add 2 more to partOffset
          partOffset += 2
        member_part = f"{dev}{member['partnum'] + partOffset}"
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
    # step through /tmp/fstab and mount the filesystems into /newroot/
    # Sort the fstab by path hierarchy.
    os.makedirs("/newroot", exist_ok=True)
    with open("/tmp/fstab", "r") as file:
      lines = file.readlines()
      lines = sorted(lines, key=lambda line:(line.split()[1]))
      for line in lines:
        line=line.rstrip()
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
    # rsync everything and copy /tmp/fstab to /newroot/etc/fstab
    print("Copying image files...")
    sh.rsync([
      "-arx",
      "/",
      "/newroot"
    ])
    sh.cp(["/tmp/fstab", "/newroot/etc/fstab"])
    print("Copy Complete.")
    print("Running restorecon to fix up security contexts...")
    sh.chroot(["/newroot", "restorecon", "-rFp", "/" ])

  def installBootLoader(self):
    # copy in a script to do the boot loader config, and switch root to that script
    # before we run the REAL init.
    
    # first we mount some stuff for the bootloader
    bindMounts = ['dev', 'sys', 'proc']
    for mount in bindMounts:
      sh.mount(['-o', 'bind', f"/{mount}", f"/newroot/{mount}"])
    
    bootdisk = self.bootdisk

    # add the kernel commandline to /etc/default/grub
    with open("/proc/cmdline", "r") as cmdline:
      cmdlineFile = cmdline.readlines()
    
    # collapse the command line into a space separated string
    cmdlinestr = ' '.join(cmdlineFile)

    newcmdline = []
    # now let's filter out some stuff the new OS doesn't need
    for arg in cmdlinestr.split(' '):
      argKey, argvalue = arg.split('=', 1)
      if argKey == 'initrd' or \
         argKey == 'rdinit' or \
         argKey.startswith('mprov') or \
         argKey == 'autorelabel' :
          continue
      newcmdline.append(arg)

    # read in the current /etc/default/grub 
    if not os.path.exists("/newroot/etc/default/grub"):
      grubfileLines = []
    else:
      with open("/newroot/etc/default/grub", "r") as grubfile:
        grubfileLines = grubfile.readlines()

    # remove the GRUB_CMDLINE_LINUX entry
    grubfileNew = [line for line in grubfileLines if not 'GRUB_CMDLINE_LINUX=' in line]
    
    # now add our new commandline
    grubfileNew.append(f"GRUB_CMDLINE_LINUX=\"{' '.join(newcmdline)}\"")

    # write out the new file
    with open("/newroot/etc/default/grub", "w") as grubfileout:
      grubfileout.writelines(grubfileNew)

    print(f"Running `grub2-install {bootdisk}`...")
    # now let's try to run the grub installer in the new root.
    sh.chroot([f"/newroot", f"grub2-mkconfig", f"-o", "/boot/grub2/grub.cfg"])

    sh.chroot([f"/newroot", "grub2-install", bootdisk ])

    # print("Configuring GRUB2 EFI setup...")
    # create the efi file
    

    # print("Configuring GRUB2 BIOS Setup...")
    # # create a bios boot grub file.
    # with open("/newroot/etc/grub2.cfg", "w") as grubfile:
    #   grubfile.write("search --no-floppy --set efi --file /efi/grub.cfg")
    #   grubfile.write("configfile ($efi)/efi/grub.cfg")

    # # unmount our stuff.
    # for mount in bindMounts:
    #   sh.umount([f"/newroot/{mount}"])
    
  def cleanupAndSwitchroot(self):
    # disable netboot

    mprovUrl = self.mprovURL
    apiKey = self.apikey

    reqHeaders = {
      'Content-Type': 'application/json',
      'Authorization': f'Api-Key {apiKey}'
    }
    try: 
      req = requests.post(f"{mprovUrl}/systems/?self", headers=reqHeaders, data='{"netboot": false}')
    except:
      print("Error: There was an issue trying to disable netboot.  You should look into this.")

    if req.status_code != 200:
      print("Error: There was an issue trying to disable netboot.  You should look into this.")
      print(f"Error: {req.text}")
      # print(f"Error: {req.status}")

    # # Unmount all mounts in /newroot
    # mounts = []
    # if os.path.exists("/proc/mounts") :
    #   with open("/proc/mounts", "r") as mtab:
    #     for line in mtab.readlines():
    #       dev, mount, opts = line.split(' ', 2)
    #       if mount.startswith("/newroot") :
    #         if(mount == "/newroot"): continue
    #         mounts.append(mount)

    # # reverse sort the list
    # mounts.sort(reverse=True)
    # for mount in mounts:
    #   sh.umount([mount])

    # shutdown the net.
    sh.pkill(['udhcp'])

    # autorelabel
    sh.touch("/newroot/.autorelabel")

    # # # Unmount //sys/ /proc/ /run/
    # # sh.umount([ "/sys", "/proc", "/run"])
    # # Switchroot to the new filesystem.
    # print("Switching to new root.... LEEEEROY JENKINS!!!.....")
    # os.makedirs("/newroot/old_root")
    # os.system("/sbin/pivot_root / /newroot/old_root")
    # os.execv("chroot","chroot /newroot sh -c 'umount /old_root; exec /bin/init' < dev/console > dev/console 2>&1")
    # # os.execl("/sbin/switch_root", "/sbin/switch_root", "/newroot", "/sbin/init")


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

  def _createPartition(self, device, disk, inpart, sectorsize, start, parttype=parted.PARTITION_NORMAL):
    part=inpart
    if part['fill']:
      geometry = parted.Geometry(
        device=device,
        start=start,
        end=device.getLength() - 1
      )
    else:
      geometry = parted.Geometry(
        device=device,
        start=start,
        length=self.from_mebibytes(part['size'],sectorsize)
      )
    if part['filesystem'] == 'linux-swap':
      part['filesystem'] = 'linux-swap(v1)'
    if part['filesystem'] == 'raid'  \
      or part['filesystem'] == None \
      or part['filesystem'] == 'efi' \
      or part['filesystem'] == 'biosboot':
      # part['filesystem'] = None
      fs=None
    else:
      fs = parted.FileSystem(
        type=part['filesystem'], 
        geometry=geometry,
      )
    partition = parted.Partition(
      disk=disk,
      type=parttype,
      fs=fs,
      geometry=geometry
    )
    disk.addPartition(partition=partition, constraint=device.optimalAlignedConstraint)
    if part['filesystem'] == 'biosboot':
      print(f"Setting bootable flag on {device.path}{part['partnum']}")
      partition.setFlag(parted.PARTITION_BIOS_GRUB)
      if device.path != self.bootdisk:
        print("ERROR: Somehow, the disk we detected was not the same as the one we are trying to set.  Bailing out.")
        sys.exit(1)
      self.bootpart = f"{self.bootdisk}{part['partnum']}"
    disk.commit()
    return self.from_mebibytes(part['size'], sectorsize)
    

  def _makeFS(self, part, pdisk):

    # if we are building an EFI partition filesystem, it's vfat
    if part['filesystem'] == "efi":
      print(f"Building EFI vfat file system on {pdisk['name']}{part['partnum']}...")
      sh.mkfs(['-t', 'vfat',f"{pdisk['diskname']}{part['partnum']}"])
      return None

    # everything else is offset by the extended and boot partitions if applicablew
    partOffset = 0
    if pdisk['diskname'] == self.bootdisk:
      # boot disk, we are going to add 2 more to partOffset
      partOffset += 2
    if part['partnum'] != '':
      part['partnum'] = int(part['partnum']) + partOffset
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
      print(f"Building {part['filesystem']} file system on {pdisk['name']}{part['partnum']}...")
      sh.mkswap(f"{pdisk['diskname']}{part['partnum']}",f"{part['uuidopt']}",  f"{part['uuid']}")
      part['mount'] = "none"
      # put this back
      part['filesystem'] = "swap"
      
    else:
      print(f"Building {part['filesystem']} file system on {pdisk['name']}{part['partnum']}...")
      sh.mkfs(f"{part['force']}", f"-t", f"{part['filesystem']}", f"{part['uuidopt']}", f"{part['uuid']}", f"{pdisk['diskname']}{part['partnum']}")
    return partuuid

def main():
  sInstaller = mProvStatefulInstaller()
  sInstaller.buildDisks()
  sInstaller.buildRAIDs()
  sInstaller.mountDisks()
  sInstaller.copyRoot()
  sInstaller.installBootLoader()
  sInstaller.cleanupAndSwitchroot()
  pass

def __main__():
    main()
    raise Exception("Installer Exitted without switch_root()")
if __name__ == "__main__":
    main()
