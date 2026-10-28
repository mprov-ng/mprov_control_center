#!/bin/bash

export PATH=$PATH:/sbin
mount -t proc proc /proc >/dev/null 2>&1
mount -t sysfs sysfs /sys >/dev/null 2>&1
mount -t devtmpfs devtmpfs /dev >/dev/null 2>&1
mount -t tmpfs tmpfs /run >/dev/null 2>&1
respawn() {
  echo "Press 'r' to restart the mProv Boot System."
  while true
  do
    read -r -n 1 -s key
    if [ "$key" == "r" ] || [ "$key" == "R" ]
    then
      echo "Restarting..."
      trap EXIT
      trap ERR
      echo "Unmounting filesystems..."
      umount -alf
      mount -t devtmpfs devtmpfs /dev
      cd /
      exit 0
    fi
  done
}

# error handler for the script
err_handler() {
  echo
  echo
  echo "Error: SOMETHING HAS GONE TERRIBLY WRONG! Press Alt-F2 for a shell!"
  respawn
}
export -f err_handler


get_kcmdline_opt(){
  # the kernel cmdline is split into words on purpose.
  # shellcheck disable=SC2013
  for i in $(cat /proc/cmdline)
  do
    tmp_str=$(echo "$i" | grep "$1")
    if [ "$tmp_str" != "" ]
    then
      echo "$tmp_str" | awk -F= '{print $NF}'
    fi
  done

}



# load the modules the kernel command line asks for (mprov_initial_mods: the
# distro's, system groups' and system's initial_mods, merged by the mPCC),
# before the drivers found by PCI class, so a listed NIC driver is there for
# provisioning.  Each one that loads goes in /tmp/init_mods, for the image's
# dracut config and the stateful installer; one that doesn't is skipped with
# a warning (#372).
load_initial_mods() {
  for mod in $(echo "$1" | tr ',' ' ')
  do
    if modprobe "$mod" >/dev/null 2>&1
    then
      echo -n "${mod}," | tee -a /tmp/init_mods
    else
      echo -n "(${mod} not loaded)," >&2
    fi
  done
}


# grab some of our variables from the kernel cmdline.
MPROV_TMPFS_SIZE=$(get_kcmdline_opt mprov_tmpfs_size)
MPROV_IMAGE_URL=$(get_kcmdline_opt mprov_image_url)
MPROV_INITIAL_MODS=$(get_kcmdline_opt mprov_initial_mods)
MPROV_PROV_INTF=$(get_kcmdline_opt mprov_prov_intf)
MPROV_STATEFUL=$(get_kcmdline_opt mprov_stateful)
MPROV_RESCUE=$(get_kcmdline_opt mprov_rescue)
export MPROV_TMPFS_SIZE MPROV_IMAGE_URL MPROV_INITIAL_MODS MPROV_PROV_INTF MPROV_STATEFUL MPROV_RESCUE
# load our initial modules
echo -n "" > /tmp/init_mods
trap err_handler EXIT
trap err_handler ERR
echo -n "Loading initial modules... "
trap ERR
load_initial_mods "$MPROV_INITIAL_MODS"
trap err_handler ERR
echo "  DONE!"

echo -n "Loading network drivers... "
echo -n "virtio_net," | tee -a /tmp/init_mods
modprobe virtio_net
for dev in /sys/bus/pci/devices/*
do
	i=${dev##*/}
	if [ -e "/sys/bus/pci/devices/$i/class" ]
	then
		class=$(cut -c -4 "/sys/bus/pci/devices/$i/class")
		if [ "$class" == "0x02" ]
		then
			# if we are class 0x02, it's a network device.
			# let's see if we can find a driver.
			modalias=$(cat "/sys/bus/pci/devices/$i/modalias")
      trap ERR
			echo -n "$(modprobe -R "$modalias")," | tee -a /tmp/init_mods
			modprobe "$modalias"
      MPROV_INITIAL_MODS="${MPROV_INITIAL_MODS},${modalias}"
      trap err_handler ERR
	fi	fi
done
echo "  DONE!"


echo -n "Loading storage drivers... "
echo -n "ahci," | tee -a /tmp/init_mods
modprobe ahci
echo -n "nvme," | tee -a /tmp/init_mods
modprobe nvme
echo -n "virtio_pci," | tee -a /tmp/init_mods
modprobe virtio_pci
echo -n "virtio_scsi," | tee -a /tmp/init_mods
modprobe virtio_scsi
echo -n "virtio_blk," | tee -a /tmp/init_mods
modprobe virtio_blk
for dev in /sys/bus/pci/devices/*
do
	i=${dev##*/}
	if [ -e "/sys/bus/pci/devices/$i/class" ]
	then
		class=$(cut -c -4 "/sys/bus/pci/devices/$i/class")
		if [ "$class" == "0x01" ]
		then
			# if we are class 0x01, it's a storage device.
			# let's see if we can find a driver.
			modalias=$(cat "/sys/bus/pci/devices/$i/modalias")
      trap ERR
			echo -n "$(modprobe -R "$modalias" | tail -n1)," | tee -a /tmp/init_mods
			modprobe "$modalias"
      MPROV_INITIAL_MODS="${MPROV_INITIAL_MODS},${modalias}"
      trap err_handler ERR
	fi	fi
done

# force load sd_mod, make sure we are able to hit the disks
modprobe sd_mod
echo -n "sd_mod" | tee -a /tmp/init_mods
echo "  DONE!"

export PATH=$PATH:/sbin:/usr/sbin
# get the interface name
MAC=$MPROV_PROV_INTF
# this works for interface names OR MAC addresses, which is nice.
MPROV_PROV_INTF=$(ip link show | grep -i -B1 "$MAC"| grep -v link | awk -F": " '{print $2}')
if [ "$MPROV_PROV_INTF" == "" ]
then
  echo
  echo "Error: Unable to find interface matching MAC: $MAC"
  echo
  err_handler
  exit 1
fi

echo "Bringing up $MPROV_PROV_INTF if it's available..."
# reset the network stack
ip addr flush dev "$MPROV_PROV_INTF" > /dev/null 2>&1
ip link set "$MPROV_PROV_INTF" down > /dev/null 2>&1
ip link set "$MPROV_PROV_INTF" up > /dev/null 2>&1
# wait a couple of seconds for the link
sleep 5
udhcpc -s /bin/default.script -b -B -i "$MPROV_PROV_INTF"

if ! ip route | grep default > /dev/null
then
  echo
  echo "Error: Unable to obtain an IP address via DHCP on $MPROV_PROV_INTF"
  echo
  err_handler
  # no return
fi
echo "Network up."
echo; 
echo;

if [ "$MPROV_RESCUE" == "1" ]
then
  echo
  # disable the error trap for the read
  trap ERR
  read -r -p "Would you like an early shell? (y/n) " -s -n 1 -t 10 early_shell
  # re-enable the error trap
  trap err_handler ERR
  if [ "$early_shell" == "y" ] || [ "$early_shell" == "Y" ] 
  then
  
    export -f get_kcmdline_opt

    echo
    echo
    echo "Press Alt-F2 to access a shell."
    respawn
  fi
fi

echo
echo -n "Creating image directory at /image... "
mkdir -p /image
mount -t tmpfs -o "size=$MPROV_TMPFS_SIZE" tmpfs /image
mkdir -p /image/tmp
date > /image/tmp/boot_timing
echo "Image directory setup."
chmod 755 /image
sleep 5

echo; echo "Downloading and extracting image to image directory... "
echo "Retrieving $MPROV_IMAGE_URL"
trap ERR
while true
do
  cd /image || exit 1
  if wget "$MPROV_IMAGE_URL" -O - | gunzip -c | tar -x
  then 
    break
  else
    echo "Unable to retrieve image.  Retrying..."
    echo "Press Alt-F2 to access a shell."
    sleep 5
  fi
done
cd /
trap err_handler ERR

# tell dracut in the image to add the drivers loaded above.  dracut stops at
# a built-in or unknown module and leaves out every driver listed after it
# (#360), so keep only the real modules of the image's kernel (ours).
MPROV_DRACUT_MODS=""
for mod in $(sed -e 's/,/ /g' /tmp/init_mods)
do
  case " ${MPROV_DRACUT_MODS} " in *" ${mod} "*) continue ;; esac
  if chroot /image /usr/sbin/modinfo -k "$(uname -r)" -n "$mod" >/dev/null 2>&1
  then
    MPROV_DRACUT_MODS="${MPROV_DRACUT_MODS} ${mod}"
  fi
done
mkdir -p /image/etc/dracut.conf.d/
echo "add_drivers+=\"${MPROV_DRACUT_MODS} \"" > /image/etc/dracut.conf.d/mprov_mods.conf

# set the address generation mode to not privacy and generate from MAC address, applies to GUA and LL IPv6 addresses.
echo -e "[connection]\nipv6.addr-gen-mode=0\nipv6.ip6-privacy=0" > /image/etc/NetworkManager/conf.d/99.mprov-ipv6.conf

# copy resolv.conf into the image 
/bin/cp /etc/resolv.conf /image/etc/resolv.conf

echo "Image Extracted."
mount -t proc proc /image/proc
mount -t sysfs sysfs /image/sys
mount -t devtmpfs devtmpfs /image/dev/
mount -t tmpfs tmpfs /image/run

# only generate interface files on a validated system.
if [ ! -e /image/etc/mprov/nads.yaml ]
then
    
  echo "Generating Network Interface files"
  # not a typo, strips 2 entries off the end of the IMAGE url.
  mprovURL=$(dirname "$MPROV_IMAGE_URL")
  mprovURL=$(dirname "$mprovURL")
  wget -q -O /image/tmp/mprov_genNetworkInterfaces.py "${mprovURL}/static/genNetworkInterfaces.py"
  /bin/chmod 755 /image/tmp/mprov_genNetworkInterfaces.py
  chroot /image/ /usr/bin/python3 /tmp/mprov_genNetworkInterfaces.py
fi


echo -n "Starting mProv for: "
if [ "$MPROV_STATEFUL" == "1" ] && [ ! -e /image/etc/mprov/nads.yaml ]
then
  echo "Stateful Installation"
 
  # copy the stateful installer to the /image root
  wget -q -O /image/tmp/mprov_stateful.py "${mprovURL}/static/mprov_stateful.py"
  wget -q -O /image/tmp/mprov_stateful.sh "${mprovURL}/static/mprov_stateful.sh"
  /bin/chmod 755 /image/tmp/mprov_stateful.py /image/tmp/mprov_stateful.sh
  
  if [ ! -f /image/etc/resolv.conf ]
  then
    /bin/cp /etc/resolv.conf /image/etc/resolv.conf
  fi

  # mount devpts
  mkdir -p /image/dev/pts
  mount -t devpts devpts /image/dev/pts


  if [ "$MPROV_RESCUE" == "1" ]
  then  
    # enter maintenance mode in the downloaded image.
    echo "Give the root password for maintenance mode"
    chroot /image /bin/setsid /bin/login -p  root <> /dev/tty1 >&0 2>&1  
  fi
  
  # here, we run the stateful installer, to provision the disks.
  # Then we can drop out and switch to the new root.
  chroot /image /bin/bash -c "/tmp/mprov_stateful.sh"
  # make the /newroot mount point
  mkdir -p /newroot
  # move the new root out of /image
  mount --move /image/newroot /newroot
  trap ERR  
  # unmount the old image, we don't need it anymore.
  umount -f -R -l /image
  # move the mount point for /newroot to /image.
  mount --move /newroot /image 
else
  echo "Stateless Installation"

  # label the tmpfs root for SELinux (#348).  The image tarball carries no
  # labels, and tmpfs drops labels set before a policy is loaded, so load the
  # image's policy here and then relabel.  /run and /dev were mounted above
  # before the policy existed, and systemd only relabels them when it loads
  # the policy itself, so relabel them too.
  MPROV_SELINUX=$(sed -n 's/^SELINUX=//p' /image/etc/selinux/config 2>/dev/null)
  MPROV_SELINUXTYPE=$(sed -n 's/^SELINUXTYPE=//p' /image/etc/selinux/config 2>/dev/null)
  if [ -n "$MPROV_SELINUX" ] && [ "$MPROV_SELINUX" != "disabled" ] && ! grep -qw 'selinux=0' /proc/cmdline
  then
    echo "Applying SELinux labels to the image... "
    if chroot /image /usr/sbin/load_policy -i && \
      chroot /image /usr/sbin/setfiles -F -e /proc -e /sys -e /dev -e /run \
        "/etc/selinux/${MPROV_SELINUXTYPE}/contexts/files/file_contexts" / && \
      chroot /image /usr/sbin/restorecon -R /run /dev
    then
      echo "SELinux labels applied."
    else
      echo "Warning: unable to apply SELinux labels; logins may fail unless booted with enforcing=0 or selinux=0."
    fi
  fi

  # note we are not expecting to return from this.
  echo "Switching to new root.... LEEEEROY JENKINS!!!....."
  date >> /image/tmp/boot_timing
  trap EXIT
  trap ERR
  umount /sys
  umount /dev
  umount /run
  umount /proc
  ln -sf /sbin/init /image/init
  ln -sf /sbin/init /init
  kill -s SIGQUIT 1
  exit 0
fi

# echo "Shutting down network"
# pkill udhcpc
# ifconfig $MPROV_PROV_INTF down
# ip link set $MPROV_PROV_INTF down

# disable error trap
trap ERR
# oldIFS=$IFS
# IFS=,
# echo "Attempting to unload modules:"
# for mod in $MPROV_INITIAL_MODS
# do  
#   ret=1
  
#   if [ "$mod" != "" ]
#   then
#     echo -en "\t*** $mod"
#     /sbin/modprobe -r $mod > /dev/null 2>&1
#     ret=$?
#     retry=$((retry+1))
#     if [ $ret == 0 ]
#     then
#       echo " ... DONE"
#     else
#       echo " ... FAILED"
#       sleep 1
#     fi
#   else
#     ret=0
#   fi

# done
# IFS=$oldIFS

# disable trap
trap EXIT
if [ "$MPROV_RESCUE" != "1" ]
then 
  # note we are not expecting to return from this.
  echo "Switching to new root.... LEEEEROY JENKINS!!!....."
  date >> /image/tmp/boot_timing
  umount /sys
  umount /dev
  umount /run
  umount /proc
  ln -sf /sbin/init /image/init
  ln -sf /sbin/init /init
  sync; sync; sync
  # all done, reboot hard

  # unmount the installed filesystems cleanly first: a hard reboot leaves
  # the XFS log dirty, and GRUB doesn't replay it, so it can't find its
  # own files (#347).  Deepest first; read-only if one won't unmount.
  mount -t proc proc /proc >/dev/null 2>&1
  for mnt in $(awk '$2 == "/image" || $2 ~ /^\/image\// { print $2 }' /proc/mounts | sort -r)
  do
    umount "$mnt" || mount -o remount,ro "$mnt"
  done
  sync

  umount -a -f -l
  sync; sync; sync
  echo "Rebooting..."
  # the sysrq trigger lives in /proc, which was unmounted above (#347).
  mount -t proc proc /proc >/dev/null 2>&1
  echo b > /proc/sysrq-trigger
  # if that didn't reboot, ask the kernel directly.  Never fall through to
  # the exit below: init respawns this script, which would install again.
  /bin/busybox reboot -f
  sleep 10
  echo "Error: unable to reboot.  Reset this system to boot the installed OS."
  while true; do sleep 3600; done
else
  echo "Give the root password for maintenance mode"
  chroot /image /bin/setsid /bin/login -p  root <> /dev/tty1 >&0 2>&1
  echo "You are at the end of the line for rescue mode."
  echo "To restart the mProv Boot System, press 'r'."
  respawn
fi
exit 0
