#!/bin/bash

# make sure nothing is mounted in /newroot
for dir in $(mount | grep newroot | awk '{print $3}' | sort -r)
do
  umount -f "$dir"
done

if ! /usr/bin/python3 /tmp/mprov_stateful.py
then
  exit 1
fi
