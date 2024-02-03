#!/bin/bash

if [ "$DISABLE_SLURM" ]
then
  exit 0
fi
. /var/www/mprov_control_center/.env
if [ "$DB_ENGINE" != "django.db.backends.mysql" ]
then
  echo "WARN: Django isn't using the mysql backend, automatic slurmdbd config may fail."

fi


install_path=/opt/mprov/

# PRE_REQS: mlx-ofed, nvidia drivers, 

# check if the slurm binary(ies) exist and check the version?

slurmdl=/tmp/slurmdl
dlurl="https://download.schedmd.com/slurm"

getent passwd slurm > /dev/null
if [ "$?" != "0" ]
then  
  echo "Error: Unable to get 'slurm' user id.  Adding locally."
  useradd -d /export/mprov/var/slurm -u 450 slurm
fi

sudo -u slurm mkdir -p $slurmdl
cd $slurmdl

latest_file=$(curl --silent ${dlurl}/SHA1 | awk '{print $2}' | grep -v latest | grep -v "rc[0-9]\.t" | sort -t. -k1,1 -k2,2n -k3,3n | tail -n1)
latest_ver=$(echo $latest_file | sed 's/.tar.bz2//')
short_ver=$(echo $latest_ver | sed 's/slurm-//')
installed_ver=""

if [ -e $install_path/sbin/slurmd ]
then
  installed_ver=`$install_path/sbin/slurmd --version | tr ' ' '-'`
fi

if [[ "$installed_ver" == "$latest_ver" ]]; then
    printf "Already at latest slurm version (${latest_ver}).\n"
else
    echo "Installing Dependencies..."
    dnf -y install \
      pam-devel \
      munge munge-devel \
      json-c-devel \
      libyaml-devel \
      numactl-devel \
      libjwt-devel \
      http-parser-devel \
      hwloc-devel \
      hwloc \
      hwloc-plugins \
      pmix-devel \
      lz4-devel \
      freeipmi \
      rrdtool \
      dbus-devel \
      gtk2-devel \
      man2html \
      readline-devel \
      libcurl-devel \
      lua-devel \
      kmod-iser \
      kmod-kernel-mft-mlnx \
      kmod-knem \
      kmod-mlnx-ofa_kernel \
      kmod-srp \
      hcoll \
      ibutils2 \
      libibumad \
      libibverbs \
      libibverbs-utils \
      librdmacm \
      librdmacm-utils \
      mft \
      mlnx-ethtool \
      mlnx-iproute2 \
      mlnx-ofa_kernel \
      mlnx-ofa_kernel-devel \
      mstflint \
      ofed-scripts \
      python3-pyverbs \
      rdma-core \
      rdma-core-devel \
      sharp \
      
    printf "Downloading $latest_file to $slurmdl...\n"
    pushd $slurmdl
    sudo -u slurm wget -q $dlurl/$latest_file -O $latest_file
    sudo -u slurm tar -xf $latest_file
    cd $latest_ver

    sudo mkdir -p ${install_path}etc/slurm/$short_ver/pam_slurm
    sudo chown slurm ${install_path}etc/slurm/ -R
    sudo -u slurm ./configure --prefix=${install_path}/ --sysconfdir=${install_path}/etc/slurm --enable-salloc-kill-cmd --with-json --with-yaml --with-hwloc --with-munge --with-mysql_config=/usr/bin --with-hdf5=no --with-ucx --enable-pam --with-pam_dir=${install_path}etc/slurm/$short_ver/pam_slurm --with-pmix=/usr
    sudo -u slurm make -j 16
    sudo make install
    if [ "$?" == "0" ]
    then
      echo "$latest_ver" > /export/mprov/etc/slurm.version
    fi
fi        
  # enable munge
  systemctl enable munge
    
  # generate a munge key
  mkdir -p /opt/mprov/etc/munge/
  dd if=/dev/urandom bs=1 count=1024 > /opt/mprov/etc/munge/munge.key 2>/dev/null
  chown munge:munge /opt/mprov/etc/munge/munge.key 
  chmod 600  /opt/mprov/etc/munge/munge.key
  rm -rf /etc/munge
  ln -s /opt/mprov/etc/munge/ /etc/munge

  # start munge
  systemctl start munge

  # create the slurmctld service file.
  cat << EOF > /usr/lib/systemd/system/slurmctld.service
[Unit]
RequiresMountsFor=/opt/mprov
Description=Slurm controller daemon
After=network.target munge.service
ConditionPathExists=/opt/mprov/etc/slurm/slurm.conf

[Service]
Type=forking
EnvironmentFile=-/etc/sysconfig/slurmctld
ExecStart=/opt/mprov/sbin/slurmctld \$SLURMCTLD_OPTIONS
ExecReload=/bin/kill -HUP \$MAINPID
PIDFile=/var/run/slurmctld.pid
LimitNOFILE=65536
TasksMax=infinity

[Install]
WantedBy=multi-user.target

EOF

  cat << EOF > /etc/sysconfig/slurmctld
# This will let you add extra options to the slurm commandline
#export SLURMCTLD_OPTIONS=""

EOF

  cat << EOF > /usr/lib/systemd/system/slurmdbd.service
[Unit]
RequiresMountsFor=/opt/mprov
Description=SlurmDB daemon
After=network.target munge.service
ConditionPathExists=/opt/mprov/etc/slurm/slurmdbd.conf

[Service]
Type=forking
EnvironmentFile=-/etc/sysconfig/slurmdbd
ExecStart=/opt/mprov/sbin/slurmdbd \$SLURMDBD_OPTIONS
ExecReload=/bin/kill -HUP \$MAINPID
PIDFile=/var/run/slurmdbd.pid
LimitNOFILE=65536
TasksMax=infinity

[Install]
WantedBy=multi-user.target

EOF

  systemctl enable slurmctld
  mkdir -p /var/spool/slurmctld
  chown slurm /var/spool/slurmctld

  myHostname=`hostname`
  echo "SlurmctldHost=$myHostname" > /opt/mprov/etc/slurm/slurm.conf
  ctldhost=`hostname`
  echo "Creating slurm.conf"
  cat << EOF >> /opt/mprov/etc/slurm/slurm.conf
# mProv default slurm config, see /var/www/mprov_control_center/static/slurm.conf for a commented example.
ClusterName=cluster
MpiDefault=none
ProctrackType=proctrack/cgroup
ReturnToService=1
SlurmctldPidFile=/var/run/slurmctld.pid
SlurmctldPort=6817
SlurmdPidFile=/var/run/slurmd.pid
SlurmdPort=6818
SlurmdSpoolDir=/var/spool/slurmd
SlurmUser=slurm
StateSaveLocation=/var/spool/slurmctld
SwitchType=switch/none
TaskPlugin=task/cgroup
InactiveLimit=0
KillWait=30
MinJobAge=300
SlurmctldTimeout=120
SlurmdTimeout=300
Waittime=0
SchedulerType=sched/backfill
SelectType=select/cons_tres
AccountingStorageType=accounting_storage/none
JobCompType=jobcomp/none
JobAcctGatherFrequency=30
JobAcctGatherType=jobacct_gather/cgroup
SlurmctldDebug=info
SlurmctldLogFile=/var/log/slurmctld.log
SlurmdDebug=info
SlurmdLogFile=/var/log/slurmd.log
PartitionName=defq Nodes=ALL Default=YES MaxTime=INFINITE State=UP
NodeSet=ns1 Feature=compute
MaxNodeCount=20
GresTypes=gpu=

EOF
  chown slurm /opt/mprov/etc/slurm/slurm.conf
  echo "Creating cgroup.conf"
  cat << EOF > /opt/mprov/etc/slurm/cgroup.conf
CgroupMountpoint="/sys/fs/cgroup"
CgroupAutomount=no
ConstrainCores=yes
ConstrainRAMSpace=yes
ConstrainSwapSpace=no
ConstrainDevices=yes
AllowedRamSpace=100.00
AllowedSwapSpace=0.00
MemorySwappiness=100
MaxRAMPercent=100.00
MaxSwapPercent=100.00
MinRAMSpace=30
EOF
  chown slurm /opt/mprov/etc/slurm/cgroup.conf

  echo "autodetect=nvml" > /etc/mprov/etc/slurm/gres.conf
  SLURMDB_PASS=`tr -dc A-Za-z0-9 </dev/urandom | head -c 30 ; echo ''`
  echo "Creating slurmdb and user"
  cat << EOF | mysql -u root mysql
  create database slurmdb;
  CREATE USER 'slurm'@'localhost' IDENTIFIED BY '$SLURMDB_PASS';
  grant all on slurmdb.* to 'slurm'@'localhost';
  flush privileges;
EOF

  echo "Creating slurmdbd.conf"
  cat << EOF > /opt/mprov/etc/slurm/slurmdbd.conf
# slurmdbd.conf file.
#
# See the slurmdbd.conf man page for more information.
#
#
# Authentication info
AuthType=auth/munge
#
# slurmDBD info
#DebugLevel=4
LogFile=/var/log/slurmdbd
PidFile=/var/run/slurmdbd.pid
#
# Database info
SlurmUser=slurm
StorageType=accounting_storage/mysql
StoragePass=$SLURMDB_PASS
StorageHost=localhost
StorageLoc=slurmdb
StorageUser=slurm
DbdHost=localhost
EOF
  chown slurm /opt/mprov/etc/slurm/slurmdbd.conf
  chmod 600 /opt/mprov/etc/slurm/slurmdbd.conf



