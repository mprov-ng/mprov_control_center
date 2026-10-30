#!/bin/bash

# make sure nothing is mounted in /newroot
for dir in $(mount | grep newroot | awk '{print $3}' | sort -r)
do
  umount -f "$dir"
done

# run the image's udev while installing, so disk layouts can name their disks
# by /dev/disk/by-id/ or by-path/ (#410).  Only block devices are processed,
# so the NICs are left alone, and the rules that would assemble old md arrays
# or activate LVM on the disks we're about to repartition are masked (an empty
# file in /run/udev/rules.d overrides the one in /usr/lib/udev/rules.d).
UDEVD=/usr/lib/systemd/systemd-udevd
UDEV_RULES_DIR=/run/udev/rules.d
UDEV_MASKED="64-md-raid-assembly.rules 65-md-incremental.rules 69-dm-lvm-metad.rules 69-dm-lvm.rules"

stop_udev() {
  if [ -n "$udev_started" ]
  then
    udevadm control --exit >/dev/null 2>&1 || pkill -f "$UDEVD" >/dev/null 2>&1
    udev_started=""
  fi
}
trap stop_udev EXIT

if [ -x "$UDEVD" ]
then
  mkdir -p "$UDEV_RULES_DIR"
  for rule in $UDEV_MASKED
  do
    : > "$UDEV_RULES_DIR/$rule"
  done
  if "$UDEVD" --daemon
  then
    udev_started=1
    udevadm trigger --action=add --subsystem-match=block
    udevadm settle --timeout=30 || echo "Warning: udev didn't settle; /dev/disk/ links may be missing."
  else
    echo "Warning: unable to start udev; disk layouts must use kernel disk names (e.g. /dev/sda)."
  fi
else
  echo "Warning: the image has no $UDEVD; disk layouts must use kernel disk names (e.g. /dev/sda)."
fi

if ! /usr/bin/python3 /tmp/mprov_stateful.py
then
  exit 1
fi
