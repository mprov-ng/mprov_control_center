#!/bin/bash

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
ln -s /bin/busybox ip
ln -s /bin/busybox /sbin/ifconfig
ln -s /bin/busybox udhcpc
ln -s /bin/busybox udhcpc6
ln -s /bin/busybox df
ln -s /bin/busybox wget
ln -s /bin/busybox tar
ln -s /bin/busybox gunzip
ln -s /bin/busybox /sbin/route
ln -s /bin/busybox resolvconf
ln -s /bin/busybox /bin/cpio
ln -s /bin/busybox /sbin/switch_root 
ln -s /bin/busybox /bin/date
ln -s /bin/busybox /bin/pkill
ln -s /bin/busybox /bin/clear
ln -s /bin/busybox /bin/chvt
ln -s /bin/busybox /bin/env
ln -s /bin/busybox /bin/awk
ln -s /bin/busybox /bin/chmod
ln -s /bin/busybox /bin/seq
ln -s /bin/busybox /bin/dirname


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
export MPROV_BOOTDISK=`get_kcmdline_opt mporv_bootdisk`

# load our initial modules
oldIFS=$IFS
IFS=,
for mod in $MPROV_INITIAL_MODS
do
  if [ "$mod" != "" ]
  then
    echo "Loading Module $mod ..."
    /sbin/modprobe $mod
  fi
done
IFS=$oldIFS


export PATH=$PATH:/sbin:/usr/sbin
echo "Bringing up $MPROV_PROV_INTF if it's available..."
# reset the network stack
ip addr flush dev $MPROV_PROV_INTF
ip link set $MPROV_PROV_INTF down
ip link set $MPROV_PROV_INTF up
# wait a couple of seconds for the link
sleep 5
udhcpc -s /bin/default.script -b

echo "Network up."
echo; 
echo;

ip addr show dev $MPROV_PROV_INTF

echo
echo -n "Creating image directory at /image... "
mkdir -p /image/tmp 
date > /image/tmp/boot_timing
mount -t tmpfs -o size=$MPROV_TMPFS_SIZE tmpfs /image
mkdir /image/tmp
date > /image/tmp/boot_timing
echo "Image directory setup."
cd /image

echo; echo "Downloading and extracting image to image directory... "
echo "Retrieving $MPROV_IMAGE_URL"
trap ERR
while [ 1 ]
do
  wget $MPROV_IMAGE_URL -O - | gunzip -c | cpio -id --quiet
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

echo -n "Generating Network Interface files"
# not a typo, strips 2 entries off the end of the IMAGE url.
mprovURL=`dirname $MPROV_IMAGE_URL`
mprovURL=`dirname $mprovURL`
wget -q -O /image/tmp/mprov_genNetworkInterfaces.py ${mprovURL}/static/genNetworkInterfaces.py
/bin/chmod 755 /image/tmp/mprov_genNetworkInterfaces.py
chroot /image/ /usr/bin/python3.8 /tmp/mprov_genNetworkInterfaces.py

echo -n "Starting mProv for: "
if [ "$MPROV_STATEFUL" == "1" ]
then
  echo "Stateful Installation"
 
  # copy the stateful installer to the /image root
  /bin/mv /tmp/mprov_stateful.py /image/tmp/mprov_stateful.py
  /bin/cp /tmp/mprov_stateful.sh /image/tmp/mprov_stateful.sh
  /bin/chmod 755 /image/tmp/mprov_stateful.py /image/tmp/mprov_stateful.sh 
  /bin/cp /etc/resolv.conf /image/etc/resolv.conf
  # mount devpts
  mkdir -p /image/dev/pts
  mount -t devpts devpts /image/dev/pts
  ln -s /proc/self/fd /image/dev/fd 
  
  # note we are not expecting to return from this.
  exec /sbin/switch_root -c /dev/console /image /tmp/mprov_stateful.sh
  

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
oldIFS=$IFS
IFS=,
for mod in $MPROV_INITIAL_MODS
do  
  if [ "$mod" != "" ]
  then
    /sbin/modprobe -r $mod
  fi
done
IFS=$oldIFS

umount /proc
umount /sys
#umount /dev
umount /run

# disable trap
trap EXIT
echo "Switching to new root.... LEEEEROY JENKINS!!!....."
date >> /image/tmp/boot_timing
exec /sbin/switch_root  -c /dev/console /image /sbin/init
echo "Something's WRONG!!!! Emergency Shell"

mount -t proc proc /proc &
mount -t sysfs sysfs /sys &
mount -t devtmpfs devtmpfs /dev &
mount -t tmpfs tmpfs /run &

# redirect stdio to tty1 and start a new process group, enables bash
# job control... hopefully
export -f get_kcmdline_opt
/bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1
