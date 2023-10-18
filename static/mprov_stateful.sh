#!/bin/bash
/usr/bin/python3.8 /tmp/mprov_stateful.py
if [ "$?" != "0" ]
then
  mount -t devtmpfs devtmpfs /dev 
  /bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1
  exit 0
fi
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