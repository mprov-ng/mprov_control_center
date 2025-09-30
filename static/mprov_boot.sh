#!/bin/bash

export PATH=$PATH:/sbin

# if this works, it would be great...
err_handler() {
  echo "Error: SOMETHING HAS GONE TERRIBLY WRONG! DROPPING TO SERIAL SHELL!"
  # redirect stdio to tty1 and start a new process group, enables bash
  # job control... hopefully
  export -f get_kcmdline_opt
  mount -t devtmpfs devtmpfs /dev 

  /bin/setsid /bin/bash -m  <> /dev/tty0 >&0 2>&1
}
export -f err_handler
echo "mProv boot setup..."
set +e
set -o pipefail
cd /bin
# install all the enabled busybox links
/bin/busybox --install


mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run

get_kcmdline_opt(){
  for i in  `cat /proc/cmdline`
  do
    tmp_str=`echo $i | grep $1`
    if [ "$tmp_str" != "" ]
    then
      echo $tmp_str | awk -F= '{print $NF}'
    fi
  done

}

trap err_handler EXIT
trap err_handler ERR

# grab some of our variables from the kernel cmdline.
export MPROV_TMPFS_SIZE=`get_kcmdline_opt mprov_tmpfs_size`
export MPROV_IMAGE_URL=`get_kcmdline_opt mprov_image_url`
export MPROV_INITIAL_MODS=`get_kcmdline_opt mprov_initial_mods`
export MPROV_PROV_INTF=`get_kcmdline_opt mprov_prov_intf`
export MPROV_STATEFUL=`get_kcmdline_opt mprov_stateful`
export MPROV_BOOTDISK=`get_kcmdline_opt mprov_bootdisk`
export MPROV_RESCUE=`get_kcmdline_opt mprov_rescue`
# load our initial modules
#oldIFS=$IFS
#IFS=,
#for mod in $MPROV_INITIAL_MODS
#do
#  if [ "$mod" != "" ]
#  then
#    echo "Loading Module $mod ..."
#    /sbin/modprobe $mod
#  fi
#done
#IFS=$oldIFS

echo -n "" > /tmp/init_mods

echo -n "Loading network drivers... "
for i in `ls -1 /sys/bus/pci/devices/`
do
	if [ -e /sys/bus/pci/devices/$i/class ]
	then
		class=`cat /sys/bus/pci/devices/$i/class | cut -c -4`
		if [ "$class" == "0x02" ]
		then
			# if we are class 0x02, it's a network device.
			# let's see if we can find a driver.
			modalias=`cat /sys/bus/pci/devices/$i/modalias`
      trap ERR
			echo -n "`modprobe -R $modalias`," | tee -a /tmp/init_mods
			modprobe $modalias
      trap err_handler ERR
	fi	fi
done
echo "  DONE!"
echo -n "Loading storage drivers... "
for i in `ls -1 /sys/bus/pci/devices/`
do
	if [ -e /sys/bus/pci/devices/$i/class ]
	then
		class=`cat /sys/bus/pci/devices/$i/class | cut -c -4`
		if [ "$class" == "0x01" ]
		then
			# if we are class 0x01, it's a storage device.
			# let's see if we can find a driver.
			modalias=`cat /sys/bus/pci/devices/$i/modalias `
      trap ERR
			echo -n "`modprobe -R $modalias  | tail -n1`," | tee -a /tmp/init_mods
			modprobe $modalias
      trap err_handler ERR
	fi	fi
done


modprobe sd_mod
echo -n "sd_mod" | tee -a /tmp/init_mods
echo "  DONE!"

export PATH=$PATH:/sbin:/usr/sbin
# get the interface name
MAC=$MPROV_PROV_INTF
MPROV_PROV_INTF=`ip link show | grep -i -B1 "$MAC"| grep -v link | awk -F": " '{print $2}'`
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
ip addr flush dev $MPROV_PROV_INTF
ip link set $MPROV_PROV_INTF down
ip link set $MPROV_PROV_INTF up
# wait a couple of seconds for the link
sleep 5
udhcpc -s /bin/default.script -b -B -i $MPROV_PROV_INTF

echo "Network up."
echo; 
echo;

ip addr show dev $MPROV_PROV_INTF
ip add



if [ "$MPROV_RESCUE" == "1" ]
then
  read -p "Would you like an early shell? (y/Y)" -t 10 early_shell
  early_shell=${early_shell:0:1}
  if [ "$early_shell" == "y" ] || [ "$early_shell" == "Y" ] 
  then
  
    echo "EMERGENCY SHELL REQUESTED!"
    export -f get_kcmdline_opt

    mount -t devtmpfs devtmpfs /dev

    /bin/setsid /bin/bash -m  <> /dev/tty0 >&0 2>&1
  fi
fi

echo
echo -n "Creating image directory at /image... "
mkdir -p /image
mount -t tmpfs -o size=$MPROV_TMPFS_SIZE tmpfs /image
mkdir -p /image/tmp
date > /image/tmp/boot_timing
mkdir -p /image/etc/dracut.conf.d/
echo -n "add_drivers+=\" " >/image/etc/dracut.conf.d/mprov_mods.conf
cat /tmp/init_mods | sed -e 's/,/ /g' >> /image/etc/dracut.conf.d/mprov_mods.conf
echo -n " \"" >> /image/etc/dracut.conf.d/mprov_mods.conf
echo "Image directory setup."
chmod 755 /image
cd /image
sleep 5

echo; echo "Downloading and extracting image to image directory... "
echo "Retrieving $MPROV_IMAGE_URL"
trap ERR
while [ 1 ]
do
  cd /image
  wget $MPROV_IMAGE_URL -O - | gunzip -c | tar -x
  if [ "$?" == "0" ]
  then 
    break
  else
    echo "Unable to retreive image.  Retrying..."
    sleep 5
  fi
done
trap err_handler ERR

# set the address generation mode to not privacy and generate from MAC address, applies to GUA and LL IPv6 addresses.
echo -e "[connection]\nipv6.addr-gen-mode=0\nipv6.ip6-privacy=0" > /image/etc/NetworkManager/conf.d/99.mprov-ipv6.conf

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
  mprovURL=`dirname $MPROV_IMAGE_URL`
  mprovURL=`dirname $mprovURL`
  wget -q -O /image/tmp/mprov_genNetworkInterfaces.py ${mprovURL}/static/genNetworkInterfaces.py
  /bin/chmod 755 /image/tmp/mprov_genNetworkInterfaces.py
  chroot /image/ /usr/bin/python3 /tmp/mprov_genNetworkInterfaces.py
fi


echo -n "Starting mProv for: "
if [ "$MPROV_STATEFUL" == "1" ] && [ ! -e /image/etc/mprov/nads.yaml ]
then
  echo "Stateful Installation"
 
  # copy the stateful installer to the /image root
  /bin/mv /tmp/mprov_stateful.py /image/tmp/mprov_stateful.py
  /bin/cp /tmp/mprov_stateful.sh /image/tmp/mprov_stateful.sh
  /bin/chmod 755 /image/tmp/mprov_stateful.py /image/tmp/mprov_stateful.sh 
  
  if [ ! -f /image/etc/resolv.conf ]
  then
    /bin/cp /etc/resolv.conf /image/etc/resolv.conf
  fi

  # mount devpts
  mkdir -p /image/dev/pts
  mount -t devpts devpts /image/dev/pts
  ln -s /proc/self/fd /image/dev/fd 
  #   export -f get_kcmdline_opt
  # # /bin/sh 
  # /bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1
  if [ "$mprov_rescue" != "1" ]
  then 
    # note we are not expecting to return from this.
    exec /sbin/switch_root -c /dev/console /image /tmp/mprov_stateful.sh
  else  
    echo "Give the root password for maintenance mode"
    chroot /image /bin/setsid /bin/login -p  root <> /dev/tty1 >&0 2>&1  
  fi

  # if we return, something bad has happened...mmmkay...
  export -f get_kcmdline_opt
  # /bin/sh 
  /bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1

else
  echo "Stateless Installation"
fi

# Stateful should never get here.
echo "Shutting down network"
pkill udhcpc
ifconfig $MPROV_PROV_INTF down
ip link set $MPROV_PROV_INTF down

# disable error trap
trap ERR
oldIFS=$IFS
IFS=,
echo "Attempting to unload modules:"
for mod in $MPROV_INITIAL_MODS
do  
  ret=1
  # retry=0
  # while [ $ret != 0 ] && [ $retry -lt 5 ]
  # do
    
    if [ "$mod" != "" ]
    then
      echo -en "\t*** $mod"
      /sbin/modprobe -r $mod > /dev/null 2>&1
      ret=$?
      retry=$((retry+1))
      if [ $ret == 0 ]
      then
        echo "DONE"
      else
        echo "FAILED"
        sleep 1
      fi
    else
      ret=0
    fi
  # done
done
IFS=$oldIFS

umount /proc
umount /sys
#umount /dev
umount /run

# disable trap
trap EXIT
if [ "$mprov_rescue" != "1" ]
then 
  # note we are not expecting to return from this.
  echo "Switching to new root.... LEEEEROY JENKINS!!!....."
  date >> /image/tmp/boot_timing
  exec /sbin/switch_root  -c /dev/console /image /sbin/init
else  
  echo "Give the root password for maintenance mode"
  chroot /image /bin/setsid /bin/login -p  root <> /dev/tty1 >&0 2>&1
fi
echo "Something's WRONG!!!! Emergency Shell"

mount -t proc proc /proc &
mount -t sysfs sysfs /sys &
mount -t devtmpfs devtmpfs /dev &
mount -t tmpfs tmpfs /run &

# redirect stdio to tty1 and start a new process group, enables bash
# job control... hopefully
export -f get_kcmdline_opt
echo "Give the root password for maintenance mode"
chroot /image /bin/setsid /bin/login -p  root <> /dev/tty1 >&0 2>&1
