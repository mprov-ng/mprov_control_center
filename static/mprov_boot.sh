#!/bin/bash

# if this works, it would be great...
err_hanlder() {
  echo "Error: SOMETHING HAS GONE TERRIBLY WRONG! DROPPING TO SERIAL SHELL!"
  # redirect stdio to tty1 and start a new process group, enables bash
  # job control... hopefully
  export -f get_kcmdline_opt
  /bin/setsid /bin/bash -m  <> /dev/ttyS0 >&0 2>&1
}

echo "mProv boot setup..."

cd /bin
ln -s /bin/busybox ip
ln -s /bin/busybox /sbin/ifconfig
ln -s /bin/busybox udhcpc
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

sleep 2
clear
chvt 1

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

trap err_hanlder ERR

# grab some of our variables from the kernel cmdline.
export MPROV_TMPFS_SIZE=`get_kcmdline_opt mprov_tmpfs_size`
export MPROV_IMAGE_URL=`get_kcmdline_opt mprov_image_url`
export MPROV_INITIAL_MODS=`get_kcmdline_opt mprov_initial_mods`
export MPROV_PROV_INTF=`get_kcmdline_opt mprov_prov_intf`

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
ip link set $MPROV_PROV_INTF up
udhcpc -s /bin/default.script

echo "Network up."

echo; 
echo;

/sbin/ifconfig $MPROV_PROV_INTF

echo
echo "Creating new root at /new_root..."
mkdir -p /new_root/tmp 
date > /new_root/tmp/boot_timing
mount -t tmpfs -o size=$MPROV_TMPFS_SIZE tmpfs /new_root
mkdir /new_root/tmp
date > /new_root/tmp/boot_timing
echo "New root setup."
cd /new_root

echo; echo "Downloading and extracting image to new root"
echo "Retrieving $MPROV_IMAGE_URL"
wget $MPROV_IMAGE_URL -O - | gunzip -c | cpio -id --quiet
echo "New root Ready."
mount -t proc proc /new_root/proc
mount -t sysfs sysfs /new_root/sys
mount -t devtmpfs devtmpfs /new_root/dev/
mount -t tmpfs tmpfs /new_root/run



echo "Shutting down network"
pkill udhcpc
ifconfig eth0 down
ip link set eth0 down
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
umount /dev
umount /run

echo "Switching to new root.... LEEEEROY JENKINS!!!....."
date >> /new_root/tmp/boot_timing
exec /sbin/switch_root -c /dev/console /new_root /sbin/init
echo "Something's WRONG!!!! Emergency Shell"

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run

# redirect stdio to tty1 and start a new process group, enables bash
# job control... hopefully
export -f get_kcmdline_opt
/bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1