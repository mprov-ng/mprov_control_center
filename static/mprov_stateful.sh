#!/bin/bash

# make sure nothing is mounted in /newroot
for dir in `mount | grep newroot | awk '{print $3}' | sort -r`
do
  umount -f $dir
done

/usr/bin/python3 /tmp/mprov_stateful.py
if [ "$?" != "0" ]
then
  mount -t devtmpfs devtmpfs /dev 
  /bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1
  exit 0
fi
# # ifconfig $MPROV_PROV_INTF down

echo "Shutting down network"
pkill udhcpc
ip addr flush dev $MPROV_PROV_INTF
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
umount /dev
umount /run

echo "Switching to new root.... LEEEEROY JENKINS!!!....."
mkdir -p /newroot/old_root
/sbin/pivot_root /newroot /newroot/old_root
for i in `mount | awk '{print $3}'| grep old_root | sort -r`
do
  umount -l $i 
done
exec /sbin/init < /dev/console > /dev/console 2>&1

mount -t devtmpfs devtmpfs /dev 
/bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1
