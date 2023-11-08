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
touch /etc/fstab
grep -qF '/export/mprov' /etc/fstab || echo '/export/mprov    /opt/mprov    none defaults,bind    0 0' >> /etc/fstab

# add it to path
cat << EOF > /etc/profile.d/99-mprov.sh
export PATH=/opt/mprov/bin:\$PATH

if [ "\$USER" == "root" ]
then
  export PATH=/opt/mprov/sbin/:/opt/mprov/bin:\$PATH
fi
EOF

# mount the bind mount
mount /opt/mprov

# Add the export to /etc/exports
touch /etc/exports
grep -qF '/export/mprov' /etc/exports || echo '/export/mprov    *(rw,no_root_squash,sync)' >> /etc/exports

# install the nfs server stuff
dnf -y install nfs-utils rpcbind
systemctl enable rpcbind
systemctl start rpcbind
systemctl enable nfs-server
systemctl start nfs-server

