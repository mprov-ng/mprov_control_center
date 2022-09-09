#!/bin/bash
which python3 

/usr/bin/python3 /tmp/mprov_stateful.py
umount /proc
umount /sys
umount /dev
umount /run


echo "Switching to new root.... LEEEEROY JENKINS!!!....."
mkdir -p /newroot/old_root
/sbin/pivot_root /newroot /newroot/old_root
umount /old_root
exec /sbin/init < /dev/console > /dev/console 2>&1

mount -t devtmpfs devtmpfs /dev 
/bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1