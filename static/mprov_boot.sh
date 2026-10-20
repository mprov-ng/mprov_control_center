#!/bin/bash

export PATH=$PATH:/sbin

echo "mProv boot setup..."
set +e
set -o pipefail
cd /bin || exit 1
# remove any old init links, mount the pseudo filesystems, then install all
# the enabled busybox links
 

rm -f /bin/init /init /sbin/init
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
/bin/busybox --install
{
  echo "::sysinit:/bin/true"
  echo "tty1::respawn:/mprov_boot_init.sh"
  echo "tty2::askfirst:-/bin/sh"
  # add a restart to re-exec init
  echo "::restart:/sbin/switch_root -c /dev/console /image /sbin/init"
} > /etc/inittab
ln -s /bin/busybox /bin/init
# disable console messages from the kernel
sysctl -w kernel.printk="1 4 1 7"
# clear the screen
echo -e "\033c"
# handoff to init, which will run our script and then switch root to the new image.
exec /bin/init
exit 0
