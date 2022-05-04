#!/bin/bash
sleep 5
clear
echo "mProv boot setup..."
echo "dropping you to a shell..."
/sbin/modprobe e1000e
cd /bin
ln -s /bin/busybox ip
ln -s /bin/busybox /sbin/ifconfig
ln -s /bin/busybox udhcpc
ln -s /bin/busybox df
ln -s /bin/busybox wget
ln -s /bin/busybox tar
ln -s /bin/busybox gzip
ln -s /bin/busybox gunzip
ln -s /bin/busybox /sbin/route
ln -s /bin/busybox resolvconf
ln -s /bin/busybox /bin/cpio
ln -s /bin/busybox /sbin/switch_root 
ln -s /bin/busybox /bin/date
ln -s /bin/busybox /bin/pkill


mount -t proc proc /proc
mount -t sysfs sysfs /sys

export PATH=$PATH:/sbin:/usr/sbin
echo "Bringing up eth0 if it's available..."
ip link set eth0 up
udhcpc -s /bin/default.script

echo "Network up."
ifconfig eth0 

echo
echo "Creating new root at /new_root..."
mkdir -p /new_root/tmp 
date > /new_root/tmp/boot_timing
mount -t tmpfs -o size=8G tmpfs /new_root
mkdir /new_root/tmp
date > /new_root/tmp/boot_timing
echo "New root setup."
cd /new_root

echo; echo "Downloading and extracting image to new root"
wget http://10.1.2.80:8080/images/compute -O - | gunzip -c | cpio -id --quiet
echo "New root Ready."
mount -t proc proc /new_root/proc
mount -t sysfs sysfs /new_root/sys

echo "Shutting down network"
pkill udhcpc
ifconfig eth0 down
ip link set eth0 down
modprobe -r e1000e
echo "Switching to new root.... LEEEEROY JENKINS!!!....."
date >> /new_root/tmp/boot_timing
exec /sbin/switch_root -c /dev/console /new_root /sbin/init
echo "Something's WRONG!!!! Emergency Shell"
/bin/bash -m