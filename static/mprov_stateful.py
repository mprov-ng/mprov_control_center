#!/usr/bin/python3

import socket
import uuid
import yaml, os, sys, time
import parted
import requests
import sh
import subprocess

# This script will:
# - grab the disklayout from the mPCC,
# - build the partition table(s)
# - build the file system(s) and any software RAID device(s)
# - write the new mounts to /tmp/fstab
# - mount all of the new filesystems under /newroot
# - rsync the RAM image to the disk and update /newroot/etc/fstab
# - install the boot loader from inside the /newroot chroot
# - clear the system's provision flag (POST systems/?self {"netboot": false}) so it boots from disk
# - exit, after which mprov_boot_init.sh reboots the system


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
  modules = ""
  rootpartUUID = ""
  # (disk layout slug, layout partition number) -> the device buildDisks() made for it
  partDevices = {}

  def __init__(self, **kwargs):
    print("mProv Stateful Installer Starting.")

    # use the script-runner config
    self.configfile = "/etc/mprov/script-runner.yaml"
    
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
      except AttributeError:
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
    except Exception:
      print("Error: Communication error to the server.", file=sys.stderr)
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
    # we error out if more than one is detected,
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

    self._checkDisks()

    print("THIS OPERATION WILL DESTROY THE CONTENTS OF THE FOLLOWING DISKS: ")
    print(f"\t{disks}")
    print("CTRL-C NOW TO STOP IT!")
    time.sleep(5)
    print("Building partitions and filesystems...")
    # stop all arrays
    sh.mdadm(['--stop', '--scan'])
    try:
      os.unlink("/tmp/fstab")
    except OSError:
      pass
    self.partDevices = {}
    print(f"Boot Disk: {self.bootdisk}")
    for pdisk in self.disklayout:
      # don't do raid disks here.
      if pdisk['dtype'] == 'mdrd':
        continue
      # partitions are numbered in the order they're created: biosboot and
      # EFI on the boot disk, then the layout's partitions by number, with
      # the fill partition last.
      partnum=1
      device = parted.getDevice(pdisk['diskname'])
      disk = parted.freshDisk(device, 'gpt' )
      
      sectorsize=device.sectorSize
      start=self.from_mebibytes(1, sectorsize)
      fillpart = None


      
      if pdisk['diskname'] == self.bootdisk:

        # clear the PMBR Boot flag from the disk
        disk.unsetFlag(parted.DISK_GPT_PMBR_BOOT)

        # if we are a boot disk, let's make a couple of needed partitions
        # create a biosboot partition
        bootpart={'filesystem': 'biosboot', 'size': 1, 'fill': False, 'partnum': 1}
        start = start + self._createPartition(device, disk, bootpart, sectorsize, start, parttype=parted.PARTITION_NORMAL)
        partnum += 1

        # create an EFI partition
        bootpart={'filesystem': 'efi', 'size': 100, 'fill': False, 'partnum': 2}
        start = start + self._createPartition(device, disk, bootpart, sectorsize, start, parttype=parted.PARTITION_NORMAL)
        self._makeFS(bootpart, pdisk)
        
        with open("/tmp/fstab", "a") as fstab:
            fstab.write(f"{self._partName(pdisk['diskname'], partnum)}\t/boot/efi\t\tvfat\tdefaults,noauto\t0 0\n")
        partnum += 1

      pdisk['partitions'] = sorted(pdisk['partitions'], key=lambda d: d['partnum'])
      for part in pdisk['partitions']:
        # if this is the fill partition, make note of that and skip for now.
        if part['fill']:
          fillpart=part
          continue
        print(f"Partition Number: {partnum}")
        start = start + self._createPartition(device, disk, part, sectorsize, start) + 1
        self._setPartDevice(pdisk, part, partnum)
        self._waitForPartition(part['device'])
        if part['filesystem'] != 'raid' and part['mount'] != 'raid':
          partuuid = self._makeFS(part, pdisk)


          # update /tmp/fstab
          with open("/tmp/fstab", "a") as fstab:
            fstab.write(f"UUID={partuuid}\t{part['mount']}\t\t{part['filesystem']}\tdefaults\t0 0\n")
          if part['mount'] == "/":
            self.rootpartUUID=f"UUID={partuuid}"
            print(self.rootpartUUID)

        partnum+=1

      if fillpart is not None:
        self._createPartition(device, disk, fillpart, sectorsize, start)    
        self._setPartDevice(pdisk, fillpart, partnum)
        self._waitForPartition(fillpart['device'])
        
        if fillpart['filesystem'] != 'raid' and fillpart['mount'] != 'raid':
          partuuid = self._makeFS(fillpart, pdisk)
          # update /tmp/fstab
          with open("/tmp/fstab", "a") as fstab:
            fstab.write(f"UUID={partuuid}\t{fillpart['mount']}\t\t{fillpart['filesystem']}\tdefaults\t0 0\n")
          if fillpart['mount'] == "/":
            self.rootpartUUID=f"UUID={partuuid}"
            print(self.rootpartUUID)
    
  def buildRAIDs(self):
    print("Building software RAID devices (if any) ... ")
    for pdisk in self.disklayout:
      # don't do raid disks here.
      if pdisk['dtype'] != 'mdrd':
        continue
      #  mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/hd[ac]1
      self.hasRAID=True
      mdadm_cmd = f"--create {pdisk['diskname']} -R --force --level={pdisk['raidlevel']} --raid-devices={len(pdisk['members'])} "
      for member in pdisk['members']:
        member_part = self.partDevices.get((member['disklayout'], member['partnum']))
        if member_part is None:
          print(f"ERROR: RAID {pdisk['diskname']} member partition {member['partnum']} of {member['disklayout']} wasn't created.")
          sys.exit(1)
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
        fstab.write(f"UUID={partuuid}\t{pdisk['mount']}\t\t{part['filesystem']}\tdefaults\t0 0\n")
      if pdisk['mount'] == "/":
        self.rootpartUUID=f"UUID={partuuid}"
        print(self.rootpartUUID)
    print("Done with RAID devices.")
    

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
  def updateFstab(self):
    currFstabLines = []
    with open("/newroot/etc/fstab") as currFstab:
      currFstabLines = currFstab.readlines()
    
    # re-arrange the lines into array of lines.
    # fstab fields are whitespace-separated; spaces in paths are escaped as \040.
    for idx,line in enumerate(currFstabLines):
      currFstabLines[idx] = line.split()
      currFstabLines[idx].append("\n")

    newFstabLines = []
    with open("/tmp/fstab") as newFstab:
      newFstabLines = newFstab.readlines()
    
    # re-arrange the lines into array of lines.
    # fstab fields are whitespace-separated; spaces in paths are escaped as \040.
    for idx,line in enumerate(newFstabLines):
      found=False
      newFstabLines[idx] = line.split()
      newFstabLines[idx].append("\n")

      for cidx, currLine in enumerate(currFstabLines):
        if currLine[1] == newFstabLines[idx][1]:
          found=True
          currFstabLines[cidx] = newFstabLines[idx]
      if not found:
        currFstabLines.append(newFstabLines[idx])
    
    # now join the current array back with 4 spaces as the separator
    # and write out the lines to the file
    with open("/newroot/etc/fstab", "w") as currFstab:
      for idx, line in enumerate(currFstabLines):
        currFstabLines[idx] = "    ".join(line)
      currFstab.writelines(currFstabLines)

  def copyRoot(self):
    # rsync everything and copy /tmp/fstab to /newroot/etc/fstab
    print("Copying image files...")
    sh.rsync([
      "-arx",
      "/",
      "/newroot"
    ])
    if os.path.exists("/newroot/etc/fstab") :
      self.updateFstab()
    else:
      sh.cp(["/tmp/fstab", "/newroot/etc/fstab"])
    print("Copy Complete.")
    print("Running restorecon to fix up security contexts...")
    sh.chroot(["/newroot", "restorecon", "-rFp", "/" ])
  def installBootLoader(self):
      # configure grub, regenerate the initramfs, and install the boot loader
      # from inside the /newroot chroot.
      # first we mount some stuff for the bootloader
      bindMounts = ['dev', 'sys', 'proc']
      for mount in bindMounts:
          sh.mount(['-o', 'bind', f"/{mount}", f"/newroot/{mount}"])

      # efivars needs an explicit bind mount -- efibootmgr can't write NVRAM
      # entries from inside the chroot without it, and this RAM disk installer
      # environment doesn't propagate it into /newroot on its own.
      if os.path.exists("/sys/firmware/efi/efivars"):
          os.makedirs("/newroot/sys/firmware/efi/efivars", exist_ok=True)
          sh.mount(['-o', 'bind', "/sys/firmware/efi/efivars", "/newroot/sys/firmware/efi/efivars"])

      bootdisk = self.bootdisk

      # add the kernel commandline to /etc/default/grub
      with open("/proc/cmdline", "r") as cmdline:
          cmdlineFile = cmdline.readlines()

      # collapse the command line into a space separated string
      cmdlinestr = ' '.join(cmdlineFile)
      newcmdline = []

      # now let's filter out some stuff the new OS doesn't need
      for arg in cmdlinestr.split(' '):
          try:
              argKey, argvalue = arg.split('=', 1)
              if argKey == 'initrd' or \
                  argKey == 'rdinit' or \
                  argKey.startswith('mprov') or \
                  argKey == 'autorelabel' :
                  if argKey == "mprov_initial_mods":
                      self.modules = argvalue.replace(",", " ")
                  continue
              newcmdline.append(arg)
          except Exception:
              pass

      # check for auto-detected modules
      if os.path.exists("/tmp/init_mods") :
          with open("/tmp/init_mods") as mods:
              for mod in mods:
                  self.modules += " " + mod.replace(",", " ")

      # append the RAID options to the command line so the initramfs assembles any RAID devices (always added, RAID or not).
      newcmdline.append("rd.md=1")
      newcmdline.append("rd.md.conf=1")
      newcmdline.append("rd.auto=1")

      # read in the current /etc/default/grub
      if not os.path.exists("/newroot/etc/default/grub"):
          grubfileLines = []
      else:
          with open("/newroot/etc/default/grub", "r") as grubfile:
              grubfileLines = grubfile.readlines()

      # remove the GRUB_CMDLINE_LINUX entry
      grubfileNew = [line for line in grubfileLines if 'GRUB_CMDLINE_LINUX=' not in line]

      # now add our new commandline
      grubfileNew.append(f"GRUB_CMDLINE_LINUX=\"{' '.join(newcmdline)} root={self.rootpartUUID}\"")

      # write out the new file
      with open("/newroot/etc/default/grub", "w") as grubfileout:
          grubfileout.writelines(grubfileNew)

      print("Regenerating initial ramdisk... ")
      try:
          sh.chroot(["/newroot", "mount", "-t", "proc", "none", "/proc"])
      except Exception:
          pass
      dracut_cmd = ["/newroot", "dracut", "--regenerate-all", "-f", "-vvv", "--mdadmconf", "--force-add", "mdraid"]
      # build a generic initramfs, with every storage driver, so the node
      # finds its root disk on first boot (#352).  Also add the drivers the
      # boot command line asked for (mprov_initial_mods).
      dracut_cmd.append("--no-hostonly")
      modules = self.realModules(self.modules.split())
      if modules:
          dracut_cmd += ["--add-drivers", " ".join(modules)]
      print(dracut_cmd)
      result = sh.chroot(dracut_cmd, _err_to_out=True)
      with open("/newroot/tmp/dracut.out", "w") as out:
          out.writelines(result)

      print("Installing boot loader...")
      # Check [ -d /sys/firmware/efi ] && echo UEFI || echo BIOS
      if os.path.exists("/sys/firmware/efi"):
          print("Configuring GRUB2 EFI Setup...")
          try:
              sh.chroot(["/newroot", "dnf", "-y", "install", "shim", "grub2-efi-*", "grub2-common", "efibootmgr"])
          except Exception:
              pass
          sh.chroot(["/newroot", "dnf", "-y", "reinstall", "shim", "grub2-efi-*", "grub2-common", "efibootmgr"])
          sh.chroot(["/newroot", "grub2-mkconfig", "-o", "/etc/grub2-efi.cfg"])
          sh.chroot(["/newroot", "grub2-mkconfig", "-o", "/boot/grub2/grub2-efi.cfg"])

          # ---- register the boot entry in firmware NVRAM ----
          # grub2-efi's RPM %posttrans scriptlet normally does this on a live
          # system, but it silently no-ops here since we're inside a chroot
          # built from a RAM disk installer rather than a booted target.
          print("Registering EFI boot entry with firmware...")

          espPartNum = "2"  # matches the EFI partition hardcoded in buildDisks()
          entryLabel = "Linux Bootloader"

          espSearch = sh.chroot(
              ["/newroot", "find", "/boot/efi/EFI", "-iname", "shimx64.efi"],
              _err_to_out=True
          )
          loaderCandidates = [line.strip() for line in espSearch.splitlines() if line.strip()]

          if not loaderCandidates:
              print("ERROR: Could not locate shimx64.efi under /boot/efi/EFI. Skipping firmware boot entry.")
          else:
              loaderPath = loaderCandidates[0].replace("/boot/efi", "").replace("/", "\\")

              # idempotency: remove any prior entries with the same label
              existing = sh.chroot(["/newroot", "efibootmgr", "-v"], _err_to_out=True)
              for line in existing.splitlines():
                  if entryLabel in line and line.strip().startswith("Boot"):
                      bootnum = line.strip()[4:8]
                      try:
                          print(sh.chroot(["/newroot", "efibootmgr", "-b", bootnum, "-B"]))
                      except Exception:
                        pass

              print(sh.chroot([
                  "/newroot", "efibootmgr", "--create",
                  "--disk", bootdisk,
                  "--part", espPartNum,
                  "--label", entryLabel,
                  "--loader", loaderPath
              ], _err_to_out=True))
              print(sh.chroot(["/newroot", "efibootmgr", "-v"], _err_to_out=True))

              # force the new entry to the front of BootOrder
              orderOut = sh.chroot(["/newroot", "efibootmgr"], _err_to_out=True)
              verboseOut = sh.chroot(["/newroot", "efibootmgr", "-v"], _err_to_out=True)

              currentOrder = None
              newNum = None
              for line in orderOut.splitlines():
                  if line.startswith("BootOrder:"):
                      currentOrder = line.split(":")[1].strip()
              for line in verboseOut.splitlines():
                  if entryLabel in line and line.strip().startswith("Boot"):
                      newNum = line.strip()[4:8]

              if currentOrder and newNum:
                  rest = ",".join([n for n in currentOrder.split(",") if n != newNum])
                  sh.chroot(["/newroot", "efibootmgr", "--bootorder", f"{newNum},{rest}"], _err_to_out=True)

      else:
          print("Configuring GRUB2 BIOS Setup...")
          with open("/newroot/etc/default/grub", "a") as gd:
              gd.write("\nGRUB_ENABLE_BLSCFG=false")
          sh.chroot([
              "/newroot",
              "grub2-install",
              "--boot-directory=/boot",
              "--recheck",
              "--verbose",
              bootdisk ])
          sh.chroot(["/newroot", "grub2-mkconfig", "-o", "/etc/grub2.cfg"])

  def realModules(self, mods):
      # dracut stops at a built-in or unknown module and leaves out every
      # driver listed after it (#360), so keep only the ones that are a
      # module for every kernel installed in /newroot.
      kernels = os.listdir("/newroot/lib/modules")
      keep = []
      for mod in mods:
          if mod in keep:
              continue
          if all(subprocess.run(["chroot", "/newroot", "modinfo", "-k", kernel, "-n", mod],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                 for kernel in kernels):
              keep.append(mod)
          else:
              print(f"Leaving {mod} out of the initramfs: it's built in, or not a module of the installed kernel.")
      return keep

  def cleanupAndSwitchroot(self):
    # disable netboot

    # XXX: the unmount and switch_root steps below are commented out and need
    # more testing; mprov_boot_init.sh reboots the system instead.
    mprovUrl = self.mprovURL
    apiKey = self.apikey

    reqHeaders = {
      'Content-Type': 'application/json',
      'Authorization': f'Api-Key {apiKey}'
    }
    try: 
      req = requests.post(f"{mprovUrl}/systems/?self", headers=reqHeaders, data='{"netboot": false}')
    except Exception as e:
      print("Error: There was an issue trying to disable netboot.  You should look into this.")
      print(f"Error: {e}")
      exit(1)
    
    try:
      if req.status_code != 200:
        print("Error: There was an issue trying to disable netboot.  You should look into this.")
        print(f"Error: {req.text}")
    except Exception as e:
      print(f"Error: {e}")

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
    try:
      sh.pkill(['udhcp'])
    except Exception:
      pass

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
      except Exception:
        print("Error: Unable to parse server response.")
        sys.exit(1)
      self.disklayout = systemDetails['disks']
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
      or part['filesystem'] is None \
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
    # the flag sets the GPT partition type; other filesystems keep parted's
    # default (Linux filesystem).  The pyparted in the images has no
    # PARTITION_ESP constant, so look the ESP flag up by name.
    if part['filesystem'] == 'efi':
      partition.setFlag(next(flag for flag, name in parted.partitionFlag.items() if name == 'esp'))
    elif part['filesystem'] == 'raid':
      partition.setFlag(parted.PARTITION_RAID)
    elif part['filesystem'] == 'linux-swap(v1)':
      partition.setFlag(parted.PARTITION_SWAP)
    disk.addPartition(partition=partition, constraint=device.optimalAlignedConstraint)
    if part['filesystem'] == 'biosboot':
      print(f"Setting bios_grub flag on {self._partName(device.path, part['partnum'])}")
      partition.setFlag(parted.PARTITION_BIOS_GRUB)
      if device.path != self.bootdisk:
        print("ERROR: Somehow, the disk we detected was not the same as the one we are trying to set.  Bailing out.")
        sys.exit(1)
      self.bootpart = self._partName(self.bootdisk, part['partnum'])
    disk.commit()
    return self.from_mebibytes(part['size'], sectorsize)
    

  def _partName(self, diskname, partnum):
    """
    The device of partition partnum on disk diskname, named the kernel's way
    (#391, the same rule as mprov_scripts' localTempDisk.py): the disk's
    kernel name (a /dev/disk/by-id/ or by-path link resolves to sda) plus the
    number, with a 'p' between when the name ends in a digit (nvme0n1p1,
    mmcblk0p1, loop0p1, md0p1).
    """
    kname = os.path.basename(os.path.realpath(diskname))
    prefix = "p" if kname[-1].isdigit() else ""
    return f"/dev/{kname}{prefix}{partnum}"

  def _checkDisks(self):
    """
    Stop before touching anything if a layout's disk doesn't exist (#391).
    The installer runs without udev, so /dev/disk/by-id/ and by-path/ links
    don't exist here even though the installed system has them.
    """
    missing = [d['diskname'] for d in self.disklayout
               if d['dtype'] != 'mdrd' and not os.path.exists(d['diskname'])]
    for diskname in missing:
      print(f"ERROR: disk {diskname} doesn't exist on this node.")
      if diskname.startswith("/dev/disk/"):
        print("ERROR: /dev/disk/by-id/ and by-path/ names don't work while installing; use the kernel name (e.g. /dev/sda).")
    if missing:
      print("ERROR: fix the disk layout in the mPCC.  No disk was changed.")
      sys.exit(1)

  def _waitForPartition(self, device, timeout=30):
    """
    Wait for a partition we just created to show up (#391).  The kernel
    creates the device node after parted commits the table, so it can be
    missing for a moment (mprov_scripts saw mkswap fail with 'cannot open
    /dev/sda1').
    """
    deadline = time.monotonic() + timeout
    while not os.path.exists(device):
      if time.monotonic() > deadline:
        print(f"ERROR: {device} didn't appear within {timeout}s of creating it.")
        sys.exit(1)
      time.sleep(0.1)

  def _setPartDevice(self, pdisk, part, partnum):
    """ Note the device a layout partition got, for _makeFS() and buildRAIDs(). """
    part['device'] = self._partName(pdisk['diskname'], partnum)
    self.partDevices[(pdisk['slug'], part['partnum'])] = part['device']

  def _makeFS(self, part, pdisk):
    
    # if we are building an EFI partition filesystem, it's vfat
    if part['filesystem'] == "efi":
      dev = self._partName(pdisk['diskname'], part['partnum'])
      self._waitForPartition(dev)
      print(f"Building EFI vfat file system on {dev}...")
      sh.mkfs(['-t', 'vfat', dev])
      return None

    if part['filesystem'] == "biosboot":
      dev = self._partName(pdisk['diskname'], part['partnum'])
      self._waitForPartition(dev)
      print(f"Building biosboot ext2 file system on {dev}...")
      sh.mkfs(['-t', 'ext2', "-F", dev])
      return None
  

    # layout partitions carry the device buildDisks() made for them; a RAID
    # device is pdisk itself.
    dev = part.get('device') or pdisk['diskname']

      
    if 'format' in part:
      if part['format'] is False:
        # get the blkid.
        part['uuid'] = ""

        try:
          part['uuid'] = subprocess.run(
            ['blkid', '-o', 'value', '--match-tag=UUID', f"{dev}"],
            text=True, capture_output=True
            ).stdout.split("\n")[0]
        except Exception:
          pass
        # here we check if we got a string back from the blkid, if so, assume it's formatted
        # and return the UUID.  If not, format.
        if part['uuid'] != "":
          return part['uuid']
      
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
      print(f"Building {part['filesystem']} file system on {dev}...")
      sh.mkswap(f"{dev}",f"{part['uuidopt']}",  f"{part['uuid']}")
      part['mount'] = "none"
      # put this back
      part['filesystem'] = "swap"
      
    else:
      print(f"Building {part['filesystem']} file system on {dev}...")
      sh.mkfs("-t", f"{part['filesystem']}", f"{part['force']}", f"{part['uuidopt']}", f"{part['uuid']}", f"{dev}")
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

if __name__ == "__main__":
    main()
