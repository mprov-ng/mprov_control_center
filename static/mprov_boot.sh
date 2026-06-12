#!/bin/bash

export PATH=$PATH:/sbin

# if this works, it would be great...
err_handler() {
  echo "Error: SOMETHING HAS GONE TERRIBLY WRONG! DROPPING TO SERIAL SHELL!"
  # redirect stdio to tty1 and start a new process group, enables bash
  # job control... hopefully
  export -f get_kcmdline_opt
  mount -t devtmpfs devtmpfs /dev 

  exec /bin/setsid /bin/bash -m  <> /dev/tty0 >&0 2>&1
}
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

export -f err_handler
echo "mProv boot setup..."
set +e
set -o pipefail
cd /bin
# install all the enabled busybox links
 

rm -f /bin/init /init /sbin/init
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
/bin/busybox --install
echo "::sysinit:/bin/true" > /etc/inittab
echo "tty1::once:/mprov_boot_init.sh" >> /etc/inittab
echo "tty2::askfirst:-/bin/sh" >> /etc/inittab
# add a restart to re-exec init
echo "::restart:/sbin/switch_root -c /dev/console /image /sbin/init" >> /etc/inittab
ln -s /bin/busybox /bin/init
# disable console messages from the kernel
sysctl -w kernel.printk="1 4 1 7"
# clear the screen
echo -e "\033c"
# handoff to init, which will run our script and then switch root to the new image.
exec /bin/init
exit 0
