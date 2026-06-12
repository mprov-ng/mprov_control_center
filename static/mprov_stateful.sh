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
