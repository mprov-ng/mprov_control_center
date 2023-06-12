#!/bin/bash

if [ "$DISABLE_MPROV_SHARE" ]
then
  exit 0
fi

if [ ! -e "/export/mprov/" ]
then
  mkdir -p /export/mprov/{bin,lib,sbin,etc,usr,var}
fi

mkdir -p /opt/mprov

# Add bind mount to fstab
grep -qF '/export/mprov' /etc/fstab || echo '/export/mprov    /opt/mprov    none defaults,bind    0 0' >> /etc/fstab


# mount the bind mount
mount /opt/mprov

# Add the export to /etc/exports
grep -qF '/export/mprov' /etc/exports || echo '/export/mprov    *(rw,no_root_squash,sync)' >> /etc/exports

# install the nfs server stuff
dnf -y install nfs-utils rpcbind
systemctl enable rpcbind
systemctl start rpcbind
systemctl enable nfs-server
systemctl start nfs-server

